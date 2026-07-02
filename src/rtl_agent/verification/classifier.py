from __future__ import annotations

from pathlib import Path

from rtl_agent.implementation_models import (
    VerificationClassification,
    VerificationFailureCategory,
)
from rtl_agent.models import CommandResult

MAX_EXCERPT_LINES = 8
MAX_EXCERPT_CHARS = 600

ASSERTION_TEST_KEYWORDS = (
    "assert",
    "assertion",
    "failed",
    "failure",
    "pytest",
    "test failed",
    "error:",
    "fatal",
)
LINT_SYNTAX_KEYWORDS = (
    "syntax error",
    "parse error",
    "lint",
    "%error",
    "verilator",
    "yosys",
    "unexpected token",
)


def classify_command_result(result: CommandResult) -> VerificationClassification:
    stdout_excerpt = _excerpt(result.stdout_path)
    stderr_excerpt = _excerpt(result.stderr_path)
    text = "\n".join(stdout_excerpt + stderr_excerpt).lower()
    evidence = _evidence(stdout_excerpt, stderr_excerpt)

    if str(result.status) == "passed":
        return VerificationClassification(
            category=VerificationFailureCategory.PASSED,
            summary="command passed",
            evidence=evidence,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
        )
    if str(result.status) == "timeout":
        return VerificationClassification(
            category=VerificationFailureCategory.TIMEOUT,
            summary=result.error or "command timed out",
            evidence=evidence,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
        )
    if str(result.status) == "exec_error" and result.error:
        category = (
            VerificationFailureCategory.MISSING_EXECUTABLE
            if "executable not found" in result.error.lower()
            else VerificationFailureCategory.UNKNOWN_FAILURE
        )
        return VerificationClassification(
            category=category,
            summary=result.error,
            evidence=evidence,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
        )
    if any(keyword in text for keyword in LINT_SYNTAX_KEYWORDS):
        return VerificationClassification(
            category=VerificationFailureCategory.LINT_SYNTAX_FAILURE,
            summary="lint or syntax evidence detected",
            evidence=evidence,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
        )
    if any(keyword in text for keyword in ASSERTION_TEST_KEYWORDS):
        return VerificationClassification(
            category=VerificationFailureCategory.ASSERTION_TEST_FAILURE,
            summary="assertion or test failure evidence detected",
            evidence=evidence,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
        )
    if result.exit_code not in (None, 0):
        return VerificationClassification(
            category=VerificationFailureCategory.COMMAND_FAILURE,
            summary=f"command exited with code {result.exit_code}",
            evidence=evidence,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
        )
    return VerificationClassification(
        category=VerificationFailureCategory.UNKNOWN_FAILURE,
        summary="verification failure could not be classified",
        evidence=evidence,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
    )


def _excerpt(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines: list[str] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                stripped = raw.rstrip("\n")
                if not stripped:
                    continue
                if _is_log_framing(stripped):
                    continue
                lines.append(stripped[:MAX_EXCERPT_CHARS])
                if len(lines) >= MAX_EXCERPT_LINES:
                    break
    except OSError as exc:
        return [f"could not read excerpt: {exc}"]
    return lines


def _is_log_framing(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith("Traceback ")
        or stripped.startswith('File "')
        or stripped.startswith("File '")
    )


def _evidence(stdout_excerpt: list[str], stderr_excerpt: list[str]) -> list[str]:
    evidence: list[str] = []
    if stdout_excerpt:
        evidence.append(f"stdout: {stdout_excerpt[0]}")
    if stderr_excerpt:
        evidence.append(f"stderr: {stderr_excerpt[0]}")
    return evidence
