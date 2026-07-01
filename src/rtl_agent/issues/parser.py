from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from rtl_agent.task_contract import (
    IssueChecklistItem,
    IssueReference,
    ParsedRequirement,
    RequirementSource,
    ValidationCommand,
)

HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>.+?)\s*$")
CHECKBOX_RE = re.compile(r"^\s*(?:[-*+])\s+\[(?P<mark>[ xX])]\s+(?P<text>.+?)\s*$")
FENCE_RE = re.compile(r"^\s*```(?P<info>[A-Za-z0-9_-]*)\s*$")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
PATH_RE = re.compile(
    r"(?<![\w./-])(?P<path>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9_+-]+)?)"
)

SECTION_ALIASES = {
    "requested_behavior": {
        "requested behavior",
        "behavior",
        "objective",
        "goal",
        "summary",
        "requirements",
        "requested change",
        "problem",
    },
    "scoped_repository_context": {
        "scope",
        "repository context",
        "context",
        "files",
        "affected files",
        "paths",
        "code references",
    },
    "invariants": {"invariants", "constraints", "must preserve", "non-regression"},
    "acceptance_criteria": {"acceptance criteria", "acceptance", "done when", "definition of done"},
    "validation_commands": {"validation", "validation commands", "tests", "test plan", "checks"},
    "prohibited_shortcuts": {
        "prohibited shortcuts",
        "do not",
        "dont",
        "don't",
        "out of scope",
        "non-goals",
        "exclusions",
    },
    "evidence_requirements": {"evidence", "evidence requirements", "handoff", "reporting"},
}
AMBIGUOUS_TERMS = ("maybe", "probably", "if possible", "nice to have", "consider", "could", "might")


@dataclass
class IssueSections:
    title: str | None = None
    requested_behavior: list[ParsedRequirement] = field(default_factory=list)
    scoped_repository_context: list[IssueReference] = field(default_factory=list)
    invariants: list[ParsedRequirement] = field(default_factory=list)
    acceptance_criteria: list[ParsedRequirement] = field(default_factory=list)
    validation_commands: list[ValidationCommand] = field(default_factory=list)
    prohibited_shortcuts: list[ParsedRequirement] = field(default_factory=list)
    evidence_requirements: list[ParsedRequirement] = field(default_factory=list)
    checklist: list[IssueChecklistItem] = field(default_factory=list)
    references: list[IssueReference] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_issue_text(text: str) -> IssueSections:
    sections = IssueSections()
    current_section: str | None = None
    in_fence = False
    fence_start_line = 0
    fence_info = ""
    fence_lines: list[str] = []

    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        fence = FENCE_RE.match(line)
        if fence:
            if in_fence:
                _consume_fence(sections, current_section, fence_lines, fence_start_line, fence_info)
                in_fence = False
                fence_lines = []
                fence_info = ""
                continue
            in_fence = True
            fence_start_line = index
            fence_info = fence.group("info").lower()
            continue
        if in_fence:
            fence_lines.append(line)
            continue

        heading = HEADING_RE.match(line)
        if heading:
            heading_title = heading.group("title").strip()
            if sections.title is None and len(heading.group("level")) == 1:
                sections.title = heading_title
            current_section = _section_for_heading(heading_title)
            continue

        checkbox = CHECKBOX_RE.match(line)
        if checkbox:
            text_value = _clean_text(checkbox.group("text"))
            sections.checklist.append(
                IssueChecklistItem(
                    text=text_value,
                    checked=checkbox.group("mark").lower() == "x",
                    line=index,
                )
            )
            _add_requirement(
                sections, current_section, text_value, index, RequirementSource.CHECKLIST
            )
            _add_references(sections, text_value, index)
            continue

        bullet = BULLET_RE.match(line)
        if bullet:
            text_value = _clean_text(bullet.group("text"))
            _add_requirement(
                sections, current_section, text_value, index, RequirementSource.HEADING
            )
            _add_references(sections, text_value, index)
            continue

        stripped = line.strip()
        if stripped:
            if current_section is None and _contains_ambiguous_language(stripped):
                sections.warnings.append(f"ambiguous unsectioned prose ignored on line {index}")
            _add_inline_command_if_explicit(sections, current_section, stripped, index)
            _add_references(sections, stripped, index)

    if in_fence:
        sections.warnings.append(f"unterminated fenced block starting on line {fence_start_line}")
    _add_missing_section_warnings(sections)
    sections.references = _dedupe_references(sections.references)
    sections.scoped_repository_context = _dedupe_references(sections.scoped_repository_context)
    return sections


def _consume_fence(
    sections: IssueSections,
    current_section: str | None,
    lines: list[str],
    start_line: int,
    fence_info: str,
) -> None:
    if current_section != "validation_commands" and fence_info not in {
        "bash",
        "sh",
        "shell",
        "console",
    }:
        return
    for offset, command in enumerate(lines, start=1):
        raw = command.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("$ "):
            raw = raw[2:].strip()
        parsed = _validation_command(raw, start_line + offset, RequirementSource.FENCED_BLOCK)
        if parsed:
            sections.validation_commands.append(parsed)
        else:
            sections.warnings.append(
                f"could not parse validation command on line {start_line + offset}"
            )


def _section_for_heading(title: str) -> str | None:
    normalized = _normalize_heading(title)
    for section, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return section
    return None


def _normalize_heading(title: str) -> str:
    value = re.sub(r"[:#]+$", "", title.strip().lower())
    value = re.sub(r"[^a-z0-9' -]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _add_requirement(
    sections: IssueSections,
    current_section: str | None,
    text: str,
    line: int,
    source: RequirementSource,
) -> None:
    if not current_section:
        if _contains_ambiguous_language(text):
            sections.warnings.append(f"ambiguous unsectioned prose ignored on line {line}")
        return
    if current_section == "scoped_repository_context":
        _add_references(sections, text, line, scoped=True)
        return
    if current_section == "validation_commands":
        parsed = _validation_command(_strip_leading_command_marker(text), line, source)
        if parsed:
            sections.validation_commands.append(parsed)
        else:
            sections.warnings.append(f"validation entry is not an explicit command on line {line}")
        return
    if _contains_ambiguous_language(text):
        sections.warnings.append(f"ambiguous requirement preserved with warning on line {line}")
    target = getattr(sections, current_section)
    target.append(ParsedRequirement(text=text, line=line, source=source))


def _add_references(sections: IssueSections, text: str, line: int, scoped: bool = False) -> None:
    references: list[IssueReference] = []
    for match in PATH_RE.finditer(text):
        references.append(IssueReference(value=match.group("path"), kind="path", line=line))
    existing_values = {reference.value for reference in references}
    for item in INLINE_CODE_RE.findall(text):
        if item not in existing_values and ("/" in item or "." in Path(item).name):
            references.append(IssueReference(value=item, kind="inline_code", line=line))
    sections.references.extend(references)
    if scoped:
        sections.scoped_repository_context.extend(references)


def _add_inline_command_if_explicit(
    sections: IssueSections, current_section: str | None, text: str, line: int
) -> None:
    if current_section != "validation_commands":
        return
    raw = _strip_leading_command_marker(text)
    parsed = _validation_command(raw, line, RequirementSource.INLINE)
    if parsed:
        sections.validation_commands.append(parsed)
    else:
        sections.warnings.append(f"validation entry is not an explicit command on line {line}")


def _validation_command(raw: str, line: int, source: RequirementSource) -> ValidationCommand | None:
    if not raw or _contains_ambiguous_language(raw):
        return None
    try:
        argv = shlex.split(raw)
    except ValueError:
        return None
    if not argv:
        return None
    return ValidationCommand(command=argv, raw=raw, line=line, source=source)


def _strip_leading_command_marker(text: str) -> str:
    return text[2:].strip() if text.startswith("$ ") else text


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _contains_ambiguous_language(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in AMBIGUOUS_TERMS)


def _add_missing_section_warnings(sections: IssueSections) -> None:
    required = {
        "requested_behavior": sections.requested_behavior,
        "acceptance_criteria": sections.acceptance_criteria,
        "validation_commands": sections.validation_commands,
        "evidence_requirements": sections.evidence_requirements,
    }
    for name, values in required.items():
        if not values:
            sections.warnings.append(f"missing explicit {name.replace('_', ' ')}")


def _dedupe_references(references: list[IssueReference]) -> list[IssueReference]:
    deduped: dict[tuple[str, str, int], IssueReference] = {}
    for reference in references:
        deduped[(reference.value, reference.kind, reference.line)] = reference
    return sorted(deduped.values(), key=lambda item: (item.value, item.kind, item.line))
