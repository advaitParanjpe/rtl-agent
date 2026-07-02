from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.models import CommandResult
from rtl_agent.triage_models import (
    AssertionFailure,
    SimulatorContext,
    TriageEvidence,
    TriageReport,
    TriageSource,
    WaveformReference,
)

MAX_TRIAGE_LINES_PER_STREAM = 200
MAX_EVIDENCE_ITEMS = 24
MAX_TEXT_CHARS = 500
WAVEFORM_EXTENSIONS = (".vcd", ".fst", ".fsdb", ".wlf", ".ghw")
ASSERTION_RE = re.compile(
    r"(?i)(assert(?:ion)?(?:\s+\w+)?\s+(?:fail(?:ed|ure)?|error)|"
    r"uvm_(?:error|fatal)|fatal assertion)"
)
TIME_RE = re.compile(
    r"(?i)(?:time|@)\s*=?\s*([0-9_]+(?:\.[0-9]+)?\s*(?:fs|ps|ns|us|ms|s|cycles?)?)"
)
LABEL_RE = re.compile(
    r"(?i)(?:property|label)\s+([A-Za-z_][A-Za-z0-9_.$:-]*)|"
    r"assert(?:ion)?\s+(?!failed\b|failure\b|error\b)([A-Za-z_][A-Za-z0-9_.$:-]*)"
)
WAVEFORM_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./@:+-]+\.(?:vcd|fst|fsdb|wlf|ghw))(?=$|[\s,;)'\"`])",
    re.IGNORECASE,
)
SIMULATOR_PATTERNS = (
    ("verilator", re.compile(r"(?i)\bverilator\b|%error|%warning")),
    ("icarus", re.compile(r"(?i)\biverilog\b|\bvvp\b")),
    ("yosys", re.compile(r"(?i)\byosys\b")),
    ("cocotb", re.compile(r"(?i)\bcocotb\b")),
    ("uvm", re.compile(r"(?i)\buvm_(?:info|warning|error|fatal)\b")),
    ("time_context", re.compile(r"(?i)\b(?:time|cycle|timestamp)\b.*\b[0-9]")),
)


class TriageError(RuntimeError):
    pass


def triage_command_result(command_result_path: Path) -> TriageReport:
    resolved = command_result_path.resolve()
    try:
        result = CommandResult.model_validate_json(resolved.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise TriageError(f"could not load command result: {resolved}") from exc

    stdout_lines = _read_bounded_lines(result.stdout_path)
    stderr_lines = _read_bounded_lines(result.stderr_path)
    assertion_failures: list[AssertionFailure] = []
    waveform_references: list[WaveformReference] = []
    simulator_context: list[SimulatorContext] = []
    bounded_evidence: list[TriageEvidence] = []
    warnings: list[str] = []

    for source, lines in ((TriageSource.STDOUT, stdout_lines), (TriageSource.STDERR, stderr_lines)):
        for number, text in lines:
            assertion = _assertion_failure(source, number, text)
            if assertion and len(assertion_failures) < MAX_EVIDENCE_ITEMS:
                assertion_failures.append(assertion)
                bounded_evidence.append(TriageEvidence(source=source, line=number, text=text))
            for waveform in _waveform_references(source, number, text, result.cwd):
                if len(waveform_references) < MAX_EVIDENCE_ITEMS:
                    waveform_references.append(waveform)
                    bounded_evidence.append(TriageEvidence(source=source, line=number, text=text))
                if not waveform.exists:
                    warnings.append(f"referenced waveform file is missing: {waveform.path}")
            context = _simulator_context(source, number, text)
            if context and len(simulator_context) < MAX_EVIDENCE_ITEMS:
                simulator_context.append(context)
                bounded_evidence.append(TriageEvidence(source=source, line=number, text=text))

    return TriageReport(
        command_name=result.command_name,
        command_status=str(result.status),
        command_exit_code=result.exit_code,
        command_result_path=resolved,
        stdout_path=result.stdout_path,
        stderr_path=result.stderr_path,
        assertion_failures=sorted(assertion_failures, key=lambda item: (item.source, item.line)),
        waveform_references=sorted(
            _dedupe_waveforms(waveform_references),
            key=lambda item: (item.path, item.source, item.line),
        ),
        simulator_context=sorted(simulator_context, key=lambda item: (item.source, item.line)),
        bounded_evidence=sorted(
            _dedupe_evidence(bounded_evidence), key=lambda item: (item.source, item.line, item.text)
        )[:MAX_EVIDENCE_ITEMS],
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "Triage is deterministic and bounded to captured command stdout/stderr artifacts.",
            "Waveform files are referenced by path only; waveform contents are not interpreted.",
        ],
    )


def write_triage_report(report: TriageReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_bounded_lines(path: Path) -> list[tuple[int, str]]:
    if not path.exists():
        return []
    lines: list[tuple[int, str]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, raw in enumerate(handle, start=1):
            stripped = raw.strip()
            if stripped:
                lines.append((number, stripped[:MAX_TEXT_CHARS]))
            if number >= MAX_TRIAGE_LINES_PER_STREAM:
                break
    return lines


def _assertion_failure(source: TriageSource, line: int, text: str) -> AssertionFailure | None:
    if not ASSERTION_RE.search(text):
        return None
    label_match = LABEL_RE.search(text)
    time_match = TIME_RE.search(text)
    label = None
    if label_match:
        label = next((group for group in label_match.groups() if group), None)
    return AssertionFailure(
        source=source,
        line=line,
        summary=text,
        signal_or_label=label,
        time_context=time_match.group(1) if time_match else None,
    )


def _waveform_references(
    source: TriageSource, line: int, text: str, cwd: Path
) -> list[WaveformReference]:
    references: list[WaveformReference] = []
    for match in WAVEFORM_RE.finditer(text):
        value = match.group("path")
        path = Path(value)
        resolved = path if path.is_absolute() else (cwd / path).resolve()
        references.append(
            WaveformReference(
                source=source,
                line=line,
                path=value,
                exists=resolved.exists(),
                resolved_path=resolved if resolved.exists() else None,
                evidence=text,
            )
        )
    return references


def _simulator_context(source: TriageSource, line: int, text: str) -> SimulatorContext | None:
    for category, pattern in SIMULATOR_PATTERNS:
        if pattern.search(text):
            return SimulatorContext(source=source, line=line, category=category, text=text)
    return None


def _dedupe_waveforms(items: list[WaveformReference]) -> list[WaveformReference]:
    deduped: dict[tuple[str, TriageSource, int], WaveformReference] = {}
    for item in items:
        deduped[(item.path, item.source, item.line)] = item
    return list(deduped.values())


def _dedupe_evidence(items: list[TriageEvidence]) -> list[TriageEvidence]:
    deduped: dict[tuple[TriageSource, int, str], TriageEvidence] = {}
    for item in items:
        deduped[(item.source, item.line, item.text)] = item
    return list(deduped.values())
