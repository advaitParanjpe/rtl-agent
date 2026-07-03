from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "project/current.md",
    "project/roadmap.md",
    "project/history.md",
    "project/handoff.md",
)

STALE_DUPLICATE_PATTERNS = (
    re.compile(r"^project/current (?:2|3)\.md$"),
    re.compile(r"^project/current copy\.md$"),
    re.compile(r"^CLAUDE (?:2|3)\.md$"),
    re.compile(r"^AGENTS (?:2|3)\.md$"),
)


def main() -> int:
    errors: list[str] = []

    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).is_file():
            errors.append(f"required file is missing: {relative_path}")

    claude = _read("CLAUDE.md", errors)
    agents = _read("AGENTS.md", errors)
    handoff = _read("project/handoff.md", errors)

    if claude and "AGENTS.md" not in claude:
        errors.append("CLAUDE.md must reference AGENTS.md")
    if claude and agents:
        agent_lines = {line.strip() for line in agents.splitlines() if line.strip()}
        claude_lines = {line.strip() for line in claude.splitlines() if line.strip()}
        duplicated_lines = agent_lines & claude_lines
        if len(duplicated_lines) > 8:
            errors.append("CLAUDE.md duplicates too much AGENTS.md content")
        if len(claude.split()) > 180:
            errors.append("CLAUDE.md must remain a thin adapter")

    if handoff and "Status: ACTIVE" not in handoff and "Status: INACTIVE" not in handoff:
        errors.append("project/handoff.md must contain Status: ACTIVE or Status: INACTIVE")

    current_files = sorted(ROOT.glob("project/current*.md"))
    if current_files != [ROOT / "project/current.md"]:
        found = ", ".join(path.relative_to(ROOT).as_posix() for path in current_files)
        errors.append(f"there must be exactly one authoritative project/current.md; found {found}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or _skip_path(path):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if any(pattern.match(relative) for pattern in STALE_DUPLICATE_PATTERNS):
            errors.append(f"stale duplicate workflow file exists: {relative}")

    if errors:
        for error in errors:
            print(f"agent portability check: {error}", file=sys.stderr)
        return 1
    print("agent portability check passed")
    return 0


def _read(relative_path: str, errors: list[str]) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"could not read {relative_path}: {exc}")
        return ""


def _skip_path(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts)
    return bool(
        parts & {".git", ".venv", ".rtl-agent", "__pycache__", ".mypy_cache", ".ruff_cache"}
    )


if __name__ == "__main__":
    sys.exit(main())
