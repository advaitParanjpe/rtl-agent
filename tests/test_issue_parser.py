from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.discovery import discover_repository, write_repository_map
from rtl_agent.issues import IssueParsingError, parse_issue_file, write_task_contract
from rtl_agent.issues.parser import parse_issue_text


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


ISSUE_TEXT = """# Fix reset behavior

## Requested Behavior
- Reset must clear `rtl/top.sv` output registers.
- Maybe improve timing if possible.

## Scope
- `rtl/top.sv`
- `tb/top_tb.sv`

## Invariants
- Do not change the AXI handshake semantics.

## Acceptance Criteria
- [ ] Reset assertion drives output valid low.
- [x] Existing smoke command remains available.

## Validation Commands
```bash
python3 scripts/check.py
pytest tests/test_reset.py
```

## Prohibited Shortcuts
- Do not remove assertions.

## Evidence Requirements
- Include validation command results in the handoff.
"""


def make_repo_map(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    write(repo / "rtl" / "top.sv", "module top; endmodule\n")
    write(repo / "tb" / "top_tb.sv", "module top_tb; top dut(); endmodule\n")
    repository_map = discover_repository(repo)
    output = tmp_path / "repository-map.json"
    write_repository_map(repository_map, output)
    return output


def test_parse_issue_extracts_explicit_contract_fields(tmp_path: Path) -> None:
    issue = tmp_path / "issue.md"
    write(issue, ISSUE_TEXT)
    repository_map = make_repo_map(tmp_path)

    contract = parse_issue_file(issue, repository_map)

    assert contract.title == "Fix reset behavior"
    assert [item.text for item in contract.requested_behavior] == [
        "Reset must clear `rtl/top.sv` output registers.",
        "Maybe improve timing if possible.",
    ]
    assert "ambiguous requirement preserved with warning on line 5" in contract.warnings
    assert [item.value for item in contract.scoped_repository_context] == [
        "rtl/top.sv",
        "tb/top_tb.sv",
    ]
    assert contract.scoped_repository_context[0].in_repository_map is True
    assert [item.text for item in contract.acceptance_criteria] == [
        "Reset assertion drives output valid low.",
        "Existing smoke command remains available.",
    ]
    assert [command.raw for command in contract.validation_commands] == [
        "python3 scripts/check.py",
        "pytest tests/test_reset.py",
    ]
    assert contract.validation_commands[0].command == ["python3", "scripts/check.py"]
    assert contract.prohibited_shortcuts[0].text == "Do not remove assertions."
    assert (
        contract.evidence_requirements[0].text
        == "Include validation command results in the handoff."
    )


def test_write_task_contract_is_stable_json(tmp_path: Path) -> None:
    issue = tmp_path / "issue.md"
    write(issue, ISSUE_TEXT)
    contract = parse_issue_file(issue)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_task_contract(contract, first)
    write_task_contract(contract, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    data = json.loads(first.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1


def test_missing_sections_and_ambiguous_unsectioned_prose_are_warnings() -> None:
    parsed = parse_issue_text(
        "This could maybe be faster.\n\n## Validation\n- python3 scripts/check.py\n"
    )

    assert "ambiguous unsectioned prose ignored on line 1" in parsed.warnings
    assert "missing explicit requested behavior" in parsed.warnings
    assert "missing explicit acceptance criteria" in parsed.warnings
    assert "missing explicit evidence requirements" in parsed.warnings


def test_malformed_repository_map_fails(tmp_path: Path) -> None:
    issue = tmp_path / "issue.md"
    write(issue, ISSUE_TEXT)
    bad_map = tmp_path / "bad.json"
    write(bad_map, "{}")

    with pytest.raises(IssueParsingError, match="malformed repository map"):
        parse_issue_file(issue, bad_map)


def test_invalid_issue_path_fails(tmp_path: Path) -> None:
    with pytest.raises(IssueParsingError, match="issue path is not a file"):
        parse_issue_file(tmp_path / "missing.md")
