from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig
from rtl_agent.implementation.agent import ImplementationAgent, ImplementationError
from rtl_agent.implementation_models import ImplementationReport
from rtl_agent.providers import StubProvider
from rtl_agent.providers.base import ProviderError
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.task_contract import TaskContract


def run_bounded_implementation(
    config: AgentConfig,
    run_store: RunStore,
    provider_plan: Path,
    task_contract_path: Path,
    repository_map_path: Path,
    allowed_files: list[str],
    allowed_validation_commands: list[str],
    max_iterations: int,
) -> ImplementationReport:
    try:
        task_contract = TaskContract.model_validate_json(
            task_contract_path.read_text(encoding="utf-8")
        )
        repository_map = RepositoryMap.model_validate_json(
            repository_map_path.read_text(encoding="utf-8")
        )
        provider = StubProvider(provider_plan)
    except (OSError, ValidationError, ValueError, ProviderError) as exc:
        raise ImplementationError(f"could not load implementation inputs: {exc}") from exc

    agent = ImplementationAgent(
        config=config,
        run_store=run_store,
        provider=provider,
        task_contract=task_contract,
        repository_map=repository_map,
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        allowed_files=allowed_files,
        allowed_validation_commands=allowed_validation_commands,
        max_iterations=max_iterations,
    )
    return agent.run()


def write_implementation_report(report: ImplementationReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
