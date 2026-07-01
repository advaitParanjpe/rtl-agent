from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from rtl_agent import __version__
from rtl_agent.issues.parser import parse_issue_text
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.task_contract import IssueReference, RepositoryMapContext, TaskContract


class IssueParsingError(RuntimeError):
    pass


def parse_issue_file(issue_path: Path, repository_map_path: Path | None = None) -> TaskContract:
    resolved_issue = issue_path.resolve()
    if not resolved_issue.exists() or not resolved_issue.is_file():
        raise IssueParsingError(f"issue path is not a file: {resolved_issue}")
    try:
        text = resolved_issue.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise IssueParsingError(f"issue file is not valid UTF-8: {resolved_issue}") from exc

    parsed = parse_issue_text(text)
    repository_context = (
        _load_repository_map(repository_map_path, parsed.references)
        if repository_map_path
        else None
    )
    if repository_context:
        known = set(repository_context.matched_paths)
        unknown = set(repository_context.unmatched_paths)
        for reference in parsed.references + parsed.scoped_repository_context:
            if reference.value in known:
                reference.in_repository_map = True
            elif reference.value in unknown:
                reference.in_repository_map = False

    return TaskContract(
        tool_version=__version__,
        issue_path=resolved_issue,
        repository_map=repository_context,
        title=parsed.title,
        requested_behavior=sorted(parsed.requested_behavior, key=lambda item: item.line),
        scoped_repository_context=parsed.scoped_repository_context,
        invariants=sorted(parsed.invariants, key=lambda item: item.line),
        acceptance_criteria=sorted(parsed.acceptance_criteria, key=lambda item: item.line),
        validation_commands=sorted(parsed.validation_commands, key=lambda item: item.line),
        prohibited_shortcuts=sorted(parsed.prohibited_shortcuts, key=lambda item: item.line),
        evidence_requirements=sorted(parsed.evidence_requirements, key=lambda item: item.line),
        checklist=sorted(parsed.checklist, key=lambda item: item.line),
        warnings=sorted(dict.fromkeys(parsed.warnings)),
        parser_notes=[
            "Issue parsing is deterministic and extracts explicit headings, bullets, "
            "checkboxes, fenced commands, and path/code references.",
            "Ambiguous prose is reported as warnings; the parser does not invent "
            "requirements or plans.",
        ],
    )


def write_task_contract(contract: TaskContract, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(contract.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_repository_map(
    repository_map_path: Path, references: list[IssueReference]
) -> RepositoryMapContext:
    resolved = repository_map_path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise IssueParsingError(f"repository map path is not a file: {resolved}")
    try:
        raw = resolved.read_text(encoding="utf-8")
        repository_map = RepositoryMap.model_validate_json(raw)
    except (OSError, ValidationError, ValueError) as exc:
        raise IssueParsingError(f"malformed repository map: {resolved}") from exc

    known_paths = {record.path for record in repository_map.files}
    reference_values = sorted({reference.value for reference in references})
    matched = [value for value in reference_values if value in known_paths]
    unmatched = [value for value in reference_values if "/" in value and value not in known_paths]
    return RepositoryMapContext(
        path=resolved,
        schema_version=repository_map.schema_version,
        repository_root=repository_map.repository_root,
        file_count=len(repository_map.files),
        command_count=len(repository_map.commands),
        matched_paths=matched,
        unmatched_paths=unmatched,
    )
