"""Shared helpers for the local example-check scripts.

These scripts each drive the packaged ``rtl-agent`` CLI over the checked-in
example fixtures and assert on the resulting JSON summaries and artifacts. The
only logic they share is locating the repository root, choosing the Python
interpreter, and invoking the CLI as a subprocess; that lives here so each
example script stays focused on its own assertions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]

# Make the source tree importable so example scripts can validate CLI output
# against the typed models without requiring an installed package.
_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

_VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
PYTHON = _VENV_PYTHON if _VENV_PYTHON.exists() else Path(sys.executable)


def run_cli(args: list[str], expected_exit: int = 0) -> dict[str, Any]:
    """Run ``rtl-agent`` with ``args`` and return the parsed JSON summary.

    Raises ``AssertionError`` with captured output when the process exit code
    does not match ``expected_exit``.
    """

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        _SRC if not existing_pythonpath else f"{_SRC}{os.pathsep}{existing_pythonpath}"
    )
    result = subprocess.run(
        [str(PYTHON), "-m", "rtl_agent", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != expected_exit:
        raise AssertionError(
            "\n".join(
                [
                    f"unexpected exit for: rtl-agent {' '.join(args)}",
                    f"expected_exit: {expected_exit}",
                    f"actual_exit: {result.returncode}",
                    "stdout:",
                    result.stdout[-4000:],
                    "stderr:",
                    result.stderr[-4000:],
                ]
            )
        )
    return cast(dict[str, Any], json.loads(result.stdout))
