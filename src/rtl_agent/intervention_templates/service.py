from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ValidationError

from rtl_agent.experiment_matrix_models import (
    InterventionEntry,
    InterventionManifest,
    ReplaceEdit,
)
from rtl_agent.failure_divergence_graph_models import FailureDivergenceGraphReport, GraphNode
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.intervention_template_models import (
    ConfidenceLevel,
    DriverAnchor,
    EvidenceAnchor,
    InterventionCandidate,
    InterventionTemplateReport,
    SkippedSite,
    TemplateKind,
    TemplateSummary,
    UnsupportedTemplate,
    candidate_manifest_metadata,
)
from rtl_agent.intervention_templates.report import render_template_markdown, write_template_report
from rtl_agent.intervention_templates.templates import (
    Assignment,
    block_transition_edit,
    extract_guard_expression,
    hold_edit,
    override_condition_edit,
    parse_assignment,
    suppress_edit,
)
from rtl_agent.models import utc_now
from rtl_agent.rtl_driver_trace_models import DriverStatement, RtlDriverTraceReport, TracedSignal
from rtl_agent.run_inspection import RunInspectionError, inspect_run
from rtl_agent.signal_source_map_models import SignalSourceMapReport

_EXPERIMENT_NOTE = (
    "Experiment proposal only: this bounded edit is an evidence-anchored hypothesis to be "
    "measured with the experiment matrix, not a fix and not a causal claim."
)

_PARSER_NOTES = [
    "Intervention templates are generated read-only from existing failure-intelligence evidence "
    "(divergence graph, signal-source map, driver/dependency trace) and emitted as an explicit "
    "manifest for the experiment matrix; nothing is applied, executed, committed, or pushed.",
    "Confidence reflects only evidence completeness, never the likelihood of fixing the failure. "
    "Candidates are experiment proposals, not fixes or causal conclusions.",
]

_BOUNDED_OVERRIDE_REASON = (
    "A time-windowed signal override cannot be expressed safely with the existing patch / "
    "replace_text edit model without adding a parallel mechanism, so it is recorded as "
    "unsupported rather than generated."
)


class InterventionTemplateError(RuntimeError):
    pass


@dataclass
class _Run:
    run_dir: Path
    manifest: FailureIntelligenceRunManifest
    driver_trace: RtlDriverTraceReport
    divergence: FailureDivergenceGraphReport
    source_map: SignalSourceMapReport
    family_digest: str | None
    exact_digest: str | None


@dataclass
class _SourceFile:
    repo_relative: str
    content: str
    file_sha256: str


@dataclass
class _Builder:
    repo: Path
    commit: str
    allowed_files: list[str]
    warnings: list[str] = field(default_factory=list)
    _cache: dict[str, _SourceFile | None] = field(default_factory=dict)


def generate_interventions(
    *,
    failure_run: Path,
    repo: Path,
    allowed_files: list[str],
    output: Path,
    max_candidates: int = 8,
    reduction_report: Path | None = None,
    baseline_commit: str | None = None,
) -> InterventionTemplateReport:
    """Generate a bounded set of reviewable intervention candidates from evidence."""

    if max_candidates < 1:
        raise InterventionTemplateError("max candidates must be at least 1")
    if not allowed_files:
        raise InterventionTemplateError("at least one allowed file is required")

    run = _load_run(failure_run)
    source_repo = repo.resolve()
    commit = _resolve_commit(source_repo, baseline_commit)
    builder = _Builder(
        repo=source_repo, commit=commit, allowed_files=sorted(dict.fromkeys(allowed_files))
    )

    output_dir = output.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise InterventionTemplateError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[InterventionCandidate] = []
    skipped: list[SkippedSite] = []
    templates_considered = 0

    for leaf_evidence in _iter_signal_evidence(run):
        generated, considered, site_skips = _generate_for_signal(run, leaf_evidence, builder)
        templates_considered += considered
        candidates.extend(generated)
        skipped.extend(site_skips)

    candidates = _dedupe(candidates, skipped)
    candidates.sort(key=_ordering_key)
    if len(candidates) > max_candidates:
        for extra in candidates[max_candidates:]:
            skipped.append(
                SkippedSite(
                    template_kind=extra.template_kind,
                    signal=extra.affected_signal,
                    location=f"{extra.source_file}:{extra.source_line}",
                    reason="exceeds the maximum candidate count",
                    confidence=extra.confidence,
                )
            )
        candidates = candidates[:max_candidates]

    unsupported = [
        UnsupportedTemplate(
            template_kind=TemplateKind.BOUNDED_SIGNAL_OVERRIDE, reason=_BOUNDED_OVERRIDE_REASON
        )
    ]

    report = InterventionTemplateReport(
        generation_id=output_dir.name,
        created_at=utc_now(),
        failure_run=str(run.run_dir),
        baseline_family_digest=run.family_digest,
        baseline_exact_digest=run.exact_digest,
        target_repo=str(source_repo),
        target_commit=commit,
        allowed_files=builder.allowed_files,
        max_candidates=max_candidates,
        reduction_report=str(reduction_report) if reduction_report else None,
        earliest_divergence_time=run.divergence.global_earliest_divergence_time,
        candidates=candidates,
        skipped=skipped,
        unsupported=unsupported,
        summary=_summarize(candidates, skipped, templates_considered),
        warnings=sorted(dict.fromkeys(builder.warnings)),
        parser_notes=_PARSER_NOTES,
    )

    _write_outputs(report, output_dir, builder)
    return report


# --------------------------------------------------------------------------- #
# Evidence loading.
# --------------------------------------------------------------------------- #


def _load_run(failure_run: Path) -> _Run:
    resolved = failure_run.resolve()
    try:
        inspection = inspect_run(resolved)
    except RunInspectionError as exc:
        raise InterventionTemplateError(f"failure run could not be inspected: {exc}") from exc
    if not inspection.valid:
        raise InterventionTemplateError(
            f"refusing to use an invalid failure run: {resolved} "
            f"(status={inspection.manifest_status})"
        )

    manifest = _read_model(
        resolved / "run-manifest.json", FailureIntelligenceRunManifest, "run manifest"
    )
    driver_trace = _read_model(resolved / "driver-trace.json", RtlDriverTraceReport, "driver trace")
    divergence = _read_model(
        resolved / "divergence-graph.json", FailureDivergenceGraphReport, "divergence graph"
    )
    source_map = _read_model(
        resolved / "signal-source-map.json", SignalSourceMapReport, "signal-source map"
    )
    family_digest: str | None = None
    exact_digest: str | None = None
    try:
        fingerprint = fingerprint_run(resolved)
        family_digest = fingerprint.family_digest
        exact_digest = fingerprint.exact_digest
    except Exception as exc:  # noqa: BLE001 - fingerprint is contextual evidence, not required.
        family_digest = None
        exact_digest = None
        _ = exc
    return _Run(
        run_dir=resolved,
        manifest=manifest,
        driver_trace=driver_trace,
        divergence=divergence,
        source_map=source_map,
        family_digest=family_digest,
        exact_digest=exact_digest,
    )


def _read_model[ModelT: BaseModel](path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise InterventionTemplateError(f"{label} is unreadable: {path} ({exc})") from exc


# --------------------------------------------------------------------------- #
# Per-signal evidence assembly.
# --------------------------------------------------------------------------- #


@dataclass
class _SignalEvidence:
    leaf: str
    signal: str
    mapping_status: str
    is_root: bool
    node: GraphNode | None
    traced: TracedSignal


def _iter_signal_evidence(run: _Run) -> list[_SignalEvidence]:
    roots = set(run.divergence.root_identifiers)
    nodes = {node.identifier: node for node in run.divergence.nodes}
    status_by_leaf = {m.leaf: m.status for m in run.source_map.mappings}
    evidence: list[_SignalEvidence] = []
    for traced in run.driver_trace.traced_signals:
        if traced.status != "traced" or not traced.drivers:
            continue
        leaf = traced.leaf
        # Direct templates target only divergent (root) signals; dependency
        # registers (e.g. state-like enables) are reached via a root's guard.
        if leaf not in roots:
            continue
        node = nodes.get(leaf)
        evidence.append(
            _SignalEvidence(
                leaf=leaf,
                signal=traced.signal,
                mapping_status=str(status_by_leaf.get(leaf, traced.mapping_status)),
                is_root=leaf in roots,
                node=node,
                traced=traced,
            )
        )
    # Deterministic: roots first (closest to divergence), then by leaf name.
    evidence.sort(key=lambda e: (not e.is_root, e.leaf))
    return evidence


# --------------------------------------------------------------------------- #
# Candidate generation per signal.
# --------------------------------------------------------------------------- #


def _generate_for_signal(
    run: _Run, ev: _SignalEvidence, builder: _Builder
) -> tuple[list[InterventionCandidate], int, list[SkippedSite]]:
    candidates: list[InterventionCandidate] = []
    skipped: list[SkippedSite] = []
    considered = 0

    if ev.mapping_status not in {"exact", "probable"}:
        skipped.append(
            SkippedSite(
                template_kind=TemplateKind.SUPPRESS_ASSIGNMENT,
                signal=ev.leaf,
                reason=f"source mapping is {ev.mapping_status}; refusing to emit an edit",
            )
        )
        return candidates, considered, skipped

    base_confidence = (
        ConfidenceLevel.HIGH_EVIDENCE if ev.is_root else ConfidenceLevel.MODERATE_EVIDENCE
    )
    if ev.mapping_status == "probable":
        base_confidence = ConfidenceLevel.LOW_EVIDENCE

    failing_value = ev.node.divergence.failing_value if ev.node and ev.node.divergence else None
    primary = _primary_driver(ev.traced.drivers, failing_value)

    for driver in ev.traced.drivers:
        if _is_reset_driver(driver):
            continue
        assignment = parse_assignment(driver.statement_text, str(driver.kind))
        if assignment is None:
            continue

        direct = driver is primary
        confidence = base_confidence if direct else _weaken(base_confidence)

        # Suppress-assignment (procedural or continuous).
        considered += 1
        edit = suppress_edit(driver.statement_text, assignment)
        _emit(
            run,
            ev,
            builder,
            driver,
            assignment,
            TemplateKind.SUPPRESS_ASSIGNMENT,
            edit,
            confidence,
            candidates,
            skipped,
            hypothesis=f"Does the assignment to `{assignment.lhs}` at {driver.file_path}:"
            f"{driver.line} contribute to the observed divergence of `{ev.leaf}`?",
        )

        # Hold-register (sequential nonblocking only).
        if assignment.operator == "<=":
            considered += 1
            edit = hold_edit(driver.statement_text, assignment)
            _emit(
                run,
                ev,
                builder,
                driver,
                assignment,
                TemplateKind.HOLD_REGISTER,
                edit,
                confidence,
                candidates,
                skipped,
                hypothesis=f"Does updating register `{assignment.lhs}` at {driver.file_path}:"
                f"{driver.line} (rather than holding it) contribute to the failure of `{ev.leaf}`?",
            )

        # Override-condition (guard of this driver).
        if driver.guard:
            considered += 1
            guard_edit = override_condition_edit(driver.guard)
            _emit_guard(run, ev, builder, driver, guard_edit, confidence, candidates, skipped)

        # Block-state-transition: constant transition of a register referenced in this
        # divergent driver's own guard (state-like enable) — a grounded dependency edit.
        if direct and driver.guard:
            considered += _emit_transitions(run, ev, builder, driver, candidates, skipped)

    if not candidates and ev.traced.drivers:
        skipped.append(
            SkippedSite(
                template_kind=TemplateKind.SUPPRESS_ASSIGNMENT,
                signal=ev.leaf,
                reason="no driver produced a syntactically bounded, unambiguous edit",
            )
        )
    return candidates, considered, skipped


def _emit_transitions(
    run: _Run,
    ev: _SignalEvidence,
    builder: _Builder,
    guard_driver: DriverStatement,
    candidates: list[InterventionCandidate],
    skipped: list[SkippedSite],
) -> int:
    considered = 0
    guard_expr = extract_guard_expression(guard_driver.guard) or ""
    guard_idents = set(re.findall(r"[A-Za-z_]\w*", guard_expr))
    for traced in run.driver_trace.traced_signals:
        if traced.leaf not in guard_idents or traced.leaf == ev.leaf:
            continue
        constant_drivers = [
            d
            for d in traced.drivers
            if not _is_reset_driver(d)
            and (a := parse_assignment(d.statement_text, str(d.kind))) is not None
            and block_transition_edit(d.statement_text, a) is not None
        ]
        if len(constant_drivers) < 2:
            continue  # only clearly state-like registers
        target = constant_drivers[0]
        assignment = parse_assignment(target.statement_text, str(target.kind))
        assert assignment is not None
        considered += 1
        edit = block_transition_edit(target.statement_text, assignment)
        state_ev = _SignalEvidence(
            leaf=traced.leaf,
            signal=traced.signal,
            mapping_status=ev.mapping_status,
            is_root=False,
            node=None,
            traced=traced,
        )
        _emit(
            run,
            state_ev,
            builder,
            target,
            assignment,
            TemplateKind.BLOCK_STATE_TRANSITION,
            edit,
            ConfidenceLevel.MODERATE_EVIDENCE,
            candidates,
            skipped,
            hypothesis=f"Does the `{traced.leaf}` transition at {target.file_path}:{target.line} "
            f"(which enables the divergent update of `{ev.leaf}`) contribute to the failure?",
            enabling_signal=ev.leaf,
        )
    return considered


def _emit(
    run: _Run,
    ev: _SignalEvidence,
    builder: _Builder,
    driver: DriverStatement,
    assignment: Assignment,
    kind: TemplateKind,
    edit: tuple[str, str] | None,
    confidence: ConfidenceLevel,
    candidates: list[InterventionCandidate],
    skipped: list[SkippedSite],
    *,
    hypothesis: str,
    enabling_signal: str | None = None,
) -> None:
    if edit is None:
        return
    old, new = edit
    candidate = _build_candidate(
        run,
        ev,
        builder,
        driver,
        kind,
        old,
        new,
        confidence,
        hypothesis,
        affected_condition=None,
        enabling_signal=enabling_signal,
    )
    if isinstance(candidate, SkippedSite):
        skipped.append(candidate)
    else:
        candidates.append(candidate)


def _emit_guard(
    run: _Run,
    ev: _SignalEvidence,
    builder: _Builder,
    driver: DriverStatement,
    edit: tuple[str, str] | None,
    confidence: ConfidenceLevel,
    candidates: list[InterventionCandidate],
    skipped: list[SkippedSite],
) -> None:
    if edit is None:
        return
    old, new = edit
    hypothesis = (
        f"Does the guard `{old}` gating the update of `{ev.leaf}` at {driver.file_path}:"
        f"{driver.line} contribute to the observed failure?"
    )
    candidate = _build_candidate(
        run,
        ev,
        builder,
        driver,
        TemplateKind.OVERRIDE_CONDITION,
        old,
        new,
        confidence,
        hypothesis,
        affected_condition=old,
        enabling_signal=None,
    )
    if isinstance(candidate, SkippedSite):
        skipped.append(candidate)
    else:
        candidates.append(candidate)


def _build_candidate(
    run: _Run,
    ev: _SignalEvidence,
    builder: _Builder,
    driver: DriverStatement,
    kind: TemplateKind,
    old: str,
    new: str,
    confidence: ConfidenceLevel,
    hypothesis: str,
    *,
    affected_condition: str | None,
    enabling_signal: str | None,
) -> InterventionCandidate | SkippedSite:
    repo_file = _allowed_file_for(driver.file_path, builder.allowed_files)
    if repo_file is None:
        return SkippedSite(
            template_kind=kind,
            signal=ev.leaf,
            location=f"{driver.file_path}:{driver.line}",
            reason=f"source file {driver.file_path} is not in the allowed-file policy",
        )
    source = _committed_source(builder, repo_file)
    if source is None:
        return SkippedSite(
            template_kind=kind,
            signal=ev.leaf,
            location=f"{repo_file}:{driver.line}",
            reason=f"source file {repo_file} is not present at commit {builder.commit[:12]}",
        )
    occurrences = source.content.count(old)
    if occurrences != 1:
        return SkippedSite(
            template_kind=kind,
            signal=ev.leaf,
            location=f"{repo_file}:{driver.line}",
            reason=(
                f"edit target is ambiguous: '{old}' occurs {occurrences} times in {repo_file} "
                f"at commit {builder.commit[:12]}"
            ),
        )

    node = ev.node
    divergence_time = node.divergence.first_divergence_time if node and node.divergence else None
    evidence = EvidenceAnchor(
        signal=ev.signal,
        leaf=ev.leaf,
        mapping_status=ev.mapping_status,
        divergence_node=node.identifier if node else None,
        divergence_time=divergence_time,
        failing_value=node.divergence.failing_value if node and node.divergence else None,
        passing_value=node.divergence.passing_value if node and node.divergence else None,
        xz_difference=bool(node.divergence.xz_difference) if node and node.divergence else False,
        family_digest=run.family_digest,
        drivers=[
            DriverAnchor(
                file_path=driver.file_path,
                line=driver.line,
                statement_kind=str(driver.kind),
                statement_text=driver.statement_text,
                guard=driver.guard,
                label=str(driver.label),
            )
        ],
    )
    semantic_digest = _semantic_digest(repo_file, old, new, run.family_digest)
    candidate_id = f"{kind}-{ev.leaf}-{semantic_digest[:10]}"
    constraints = [
        "applies only under the compile configuration that reproduces the baseline failure",
        f"edit is bounded to a single span in {repo_file}",
    ]
    if enabling_signal:
        constraints.append(f"derived via the guard dependency of `{enabling_signal}`")
    return InterventionCandidate(
        candidate_id=candidate_id,
        template_kind=kind,
        hypothesis=hypothesis,
        confidence=confidence,
        file=repo_file,
        source_file=driver.file_path,
        source_line=driver.line,
        source_span_text=old,
        source_sha256=sha256(old.encode("utf-8")).hexdigest(),
        file_sha256=source.file_sha256,
        replace_old=old,
        proposed_replacement=new,
        allowed_files=[repo_file],
        affected_signal=ev.leaf,
        affected_condition=affected_condition,
        divergence_node=node.identifier if node else None,
        divergence_time=divergence_time,
        evidence=evidence,
        semantic_digest=semantic_digest,
        warnings=[],
        applicability_constraints=constraints,
        experiment_note=_EXPERIMENT_NOTE,
    )


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _primary_driver(
    drivers: list[DriverStatement], failing_value: str | None
) -> DriverStatement | None:
    candidates = [d for d in drivers if not _is_reset_driver(d)]
    if failing_value is None:
        return candidates[0] if len(candidates) == 1 else None
    matches = [d for d in candidates if _rhs_matches_value(d.statement_text, failing_value)]
    if len(matches) == 1:
        return matches[0]
    return None


def _rhs_matches_value(statement_text: str, failing_value: str) -> bool:
    fv = failing_value.strip().lower()
    text = statement_text.lower()
    if fv in {"x", "z"} or set(fv) <= {"x", "z"}:
        return "'x" in text or "'z" in text or "'hx" in text
    return f"'{fv}" in text or f"'h{fv}" in text or f"'b{fv}" in text


def _is_reset_driver(driver: DriverStatement) -> bool:
    guard = (driver.guard or "").lower()
    return "!rst_n" in guard or "!reset" in guard or "rst_n == 1'b0" in guard


def _weaken(level: ConfidenceLevel) -> ConfidenceLevel:
    order = [
        ConfidenceLevel.HIGH_EVIDENCE,
        ConfidenceLevel.MODERATE_EVIDENCE,
        ConfidenceLevel.LOW_EVIDENCE,
        ConfidenceLevel.INSUFFICIENT_EVIDENCE,
    ]
    idx = order.index(level)
    return order[min(idx + 1, len(order) - 1)]


def _allowed_file_for(driver_file_path: str, allowed_files: list[str]) -> str | None:
    normalized = driver_file_path.replace("\\", "/").lstrip("./")
    exact = [a for a in allowed_files if a == normalized]
    if exact:
        return exact[0]
    suffix = [
        a for a in allowed_files if a.endswith("/" + normalized) or Path(a).name == normalized
    ]
    if len(suffix) == 1:
        return suffix[0]
    return None


def _committed_source(builder: _Builder, repo_file: str) -> _SourceFile | None:
    if repo_file in builder._cache:
        return builder._cache[repo_file]
    result = subprocess.run(
        ["git", "-C", str(builder.repo), "show", f"{builder.commit}:{repo_file}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        builder._cache[repo_file] = None
        return None
    content = result.stdout
    source = _SourceFile(
        repo_relative=repo_file,
        content=content,
        file_sha256=sha256(content.encode("utf-8")).hexdigest(),
    )
    builder._cache[repo_file] = source
    return source


def _semantic_digest(repo_file: str, old: str, new: str, family: str | None) -> str:
    payload = "\n".join([repo_file, old, new, family or ""])
    return sha256((payload + "\n").encode("utf-8")).hexdigest()


def _dedupe(
    candidates: list[InterventionCandidate], skipped: list[SkippedSite]
) -> list[InterventionCandidate]:
    seen: dict[str, InterventionCandidate] = {}
    for candidate in candidates:
        key = candidate.semantic_digest
        if key in seen:
            skipped.append(
                SkippedSite(
                    template_kind=candidate.template_kind,
                    signal=candidate.affected_signal,
                    location=f"{candidate.file}:{candidate.source_line}",
                    reason="duplicate of an already-generated semantically equivalent edit",
                    confidence=candidate.confidence,
                )
            )
            continue
        seen[key] = candidate
    return list(seen.values())


_CONFIDENCE_RANK = {
    ConfidenceLevel.HIGH_EVIDENCE: 0,
    ConfidenceLevel.MODERATE_EVIDENCE: 1,
    ConfidenceLevel.LOW_EVIDENCE: 2,
    ConfidenceLevel.INSUFFICIENT_EVIDENCE: 3,
}

_KIND_RANK = {
    TemplateKind.SUPPRESS_ASSIGNMENT: 0,
    TemplateKind.HOLD_REGISTER: 1,
    TemplateKind.OVERRIDE_CONDITION: 2,
    TemplateKind.BLOCK_STATE_TRANSITION: 3,
    TemplateKind.BOUNDED_SIGNAL_OVERRIDE: 4,
}


def _ordering_key(candidate: InterventionCandidate) -> tuple:  # type: ignore[type-arg]
    return (
        _CONFIDENCE_RANK[ConfidenceLevel(candidate.confidence)],
        candidate.divergence_time if candidate.divergence_time is not None else 1 << 30,
        _KIND_RANK[TemplateKind(candidate.template_kind)],
        candidate.file,
        candidate.source_line,
        candidate.semantic_digest,
    )


def _summarize(
    candidates: list[InterventionCandidate], skipped: list[SkippedSite], considered: int
) -> TemplateSummary:
    def count(level: ConfidenceLevel) -> int:
        return len([c for c in candidates if ConfidenceLevel(c.confidence) == level])

    return TemplateSummary(
        templates_considered=considered,
        candidates_emitted=len(candidates),
        sites_skipped=len(skipped),
        high_evidence=count(ConfidenceLevel.HIGH_EVIDENCE),
        moderate_evidence=count(ConfidenceLevel.MODERATE_EVIDENCE),
        low_evidence=count(ConfidenceLevel.LOW_EVIDENCE),
    )


def _resolve_commit(source_repo: Path, baseline_commit: str | None) -> str:
    ref = baseline_commit or "HEAD"
    result = subprocess.run(
        ["git", "-C", str(source_repo), "rev-parse", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise InterventionTemplateError(
            f"could not resolve commit '{ref}' in {source_repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _write_outputs(report: InterventionTemplateReport, output_dir: Path, builder: _Builder) -> None:
    manifest = build_manifest(report)
    (output_dir / "interventions.json").write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    write_template_report(report, output_dir / "intervention-templates.json")
    render_template_markdown(report, output_dir / "intervention-templates.md")
    _write_diffs(report, output_dir, builder)


def build_manifest(report: InterventionTemplateReport) -> InterventionManifest:
    entries = [
        InterventionEntry(
            id=candidate.candidate_id,
            description=candidate.hypothesis,
            enabled=True,
            allowed_files=list(candidate.allowed_files),
            tags=[str(candidate.template_kind), str(candidate.confidence)],
            metadata=candidate_manifest_metadata(candidate),
            replace=ReplaceEdit(
                file=candidate.file, old=candidate.replace_old, new=candidate.proposed_replacement
            ),
        )
        for candidate in report.candidates
    ]
    return InterventionManifest(interventions=entries)


def _write_diffs(report: InterventionTemplateReport, output_dir: Path, builder: _Builder) -> None:
    diffs_dir = output_dir / "diffs"
    for candidate in report.candidates:
        source = _committed_source(builder, candidate.file)
        if source is None:
            continue
        patched = source.content.replace(candidate.replace_old, candidate.proposed_replacement, 1)
        diff = difflib.unified_diff(
            source.content.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{candidate.file}",
            tofile=f"b/{candidate.file}",
        )
        text = "".join(diff)
        if not text:
            continue
        diffs_dir.mkdir(parents=True, exist_ok=True)
        (diffs_dir / f"{candidate.candidate_id}.diff").write_text(text, encoding="utf-8")
