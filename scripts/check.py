from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
PYTHON = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)

COMMANDS = (
    [str(PYTHON), "-m", "ruff", "format", "--check", "."],
    [str(PYTHON), "-m", "ruff", "check", "."],
    [str(PYTHON), "-m", "mypy"],
    [str(PYTHON), "-m", "pytest"],
    [str(PYTHON), "scripts/e2e_example_check.py"],
    [str(PYTHON), "scripts/failure_example_check.py"],
    [str(PYTHON), "scripts/packaging_smoke.py"],
)


def main() -> int:
    for command in COMMANDS:
        print("$ " + " ".join(command), flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
