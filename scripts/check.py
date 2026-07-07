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
    [str(PYTHON), "scripts/agent_portability_check.py"],
    [str(PYTHON), "scripts/e2e_example_check.py"],
    [str(PYTHON), "scripts/failure_example_check.py"],
    [str(PYTHON), "scripts/tool_failure_example_check.py"],
    [str(PYTHON), "scripts/no_change_example_check.py"],
    [str(PYTHON), "scripts/failure_intelligence_example_check.py"],
    [str(PYTHON), "scripts/axi_router_seeded_failure_check.py"],
    [str(PYTHON), "scripts/axi_router_repository_pilot_check.py"],
    [str(PYTHON), "scripts/axi_router_ambiguity_pilot_check.py"],
    [str(PYTHON), "scripts/axi_router_simulated_failure_check.py"],
    [str(PYTHON), "scripts/axi_router_simulated_multimodule_check.py"],
    [str(PYTHON), "scripts/axi_router_simulated_triage_check.py"],
    [str(PYTHON), "scripts/external_axi_router_repo_check.py"],
    [str(PYTHON), "scripts/counterfactual_pilot_check.py"],
    [str(PYTHON), "scripts/failure_family_cluster_check.py"],
    [str(PYTHON), "scripts/counterexample_pilot_check.py"],
    [str(PYTHON), "scripts/experiment_matrix_pilot_check.py"],
    [str(PYTHON), "scripts/intervention_templates_pilot_check.py"],
    [str(PYTHON), "scripts/mvp_demo_check.py"],
    [str(PYTHON), "scripts/failure_corpus_check.py"],
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
