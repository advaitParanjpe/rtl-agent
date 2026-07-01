from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rtl_agent.artifacts import RunStore
from rtl_agent.config import AgentConfig
from rtl_agent.execution import CommandRunner
from rtl_agent.implementation_models import (
    ImplementationReport,
    ImplementationStatus,
    ProviderMessage,
    ProviderRequest,
    ProviderRole,
    ToolCall,
    ToolName,
    ToolResult,
    ValidationResultSummary,
)
from rtl_agent.providers import ModelProvider
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.task_contract import TaskContract


class ImplementationError(RuntimeError):
    pass


class ImplementationAgent:
    def __init__(
        self,
        config: AgentConfig,
        run_store: RunStore,
        provider: ModelProvider,
        task_contract: TaskContract,
        repository_map: RepositoryMap,
        task_contract_path: Path,
        repository_map_path: Path,
        allowed_files: list[str],
        allowed_validation_commands: list[str],
        max_iterations: int,
    ) -> None:
        if max_iterations < 1:
            raise ImplementationError("max iterations must be at least 1")
        self.config = config
        self.run_store = run_store
        self.provider = provider
        self.task_contract = task_contract
        self.repository_map = repository_map
        self.task_contract_path = task_contract_path.resolve()
        self.repository_map_path = repository_map_path.resolve()
        self.allowed_files = sorted(dict.fromkeys(allowed_files))
        self.allowed_validation_commands = sorted(dict.fromkeys(allowed_validation_commands))
        self.max_iterations = max_iterations
        self.repository_root = self.config.repository_root
        self._validate_inputs()

    def run(self) -> ImplementationReport:
        messages = [ProviderMessage(role=ProviderRole.USER, content=self._prompt_text())]
        tool_results: list[ToolResult] = []
        validation_results: list[ValidationResultSummary] = []
        applied_files: set[str] = set()
        warnings: list[str] = []
        failure_reason: str | None = None
        iterations = 0

        for iteration in range(1, self.max_iterations + 1):
            iterations = iteration
            request = ProviderRequest(
                task_contract_title=self.task_contract.title,
                allowed_files=self.allowed_files,
                allowed_validation_commands=self.allowed_validation_commands,
                iteration=iteration,
                messages=messages,
            )
            self._write_json(
                self.run_store.run_dir / "implementation" / f"provider-request-{iteration}.json",
                request.model_dump(mode="json"),
            )
            response = self.provider.complete(request)
            self._write_json(
                self.run_store.run_dir / "implementation" / f"provider-response-{iteration}.json",
                response.model_dump(mode="json"),
            )
            self.run_store.append_event(
                "implementation_provider_response",
                {
                    "iteration": iteration,
                    "tool_calls": len(response.tool_calls),
                    "validation_commands": response.validation_commands,
                    "stop": response.stop,
                },
            )
            messages.append(ProviderMessage(role=ProviderRole.ASSISTANT, content=response.message))

            for tool_call in response.tool_calls:
                result = self._apply_tool_call(tool_call)
                tool_results.append(result)
                if result.status == "applied":
                    applied_files.add(tool_call.path)
                if result.status == "failed":
                    failure_reason = result.message
                    break
            if failure_reason:
                break

            for command_name in response.validation_commands:
                if command_name not in self.allowed_validation_commands:
                    failure_reason = f"validation command is not allowed: {command_name}"
                    break
                command_result = CommandRunner(self.config, self.run_store).run_named(command_name)
                validation_results.append(
                    ValidationResultSummary(
                        command_name=command_name,
                        status=str(command_result.status),
                        exit_code=command_result.exit_code,
                        result_path=self.run_store.run_dir
                        / "commands"
                        / command_result.command_id
                        / "result.json",
                        stdout_path=command_result.stdout_path,
                        stderr_path=command_result.stderr_path,
                    )
                )
                if str(command_result.status) != "passed":
                    failure_reason = f"validation command failed: {command_name}"
                    break
            if failure_reason or response.stop:
                break

        diff_path = self._write_diff() if applied_files else None
        if not applied_files and failure_reason is None:
            failure_reason = "provider did not apply any edits"
        status = (
            ImplementationStatus.PROPOSED_DIFF
            if applied_files and failure_reason is None
            else ImplementationStatus.FAILED
        )
        if not validation_results:
            warnings.append("no validation commands were executed")
        report = ImplementationReport(
            status=status,
            task_contract_path=self.task_contract_path,
            repository_map_path=self.repository_map_path,
            repository_root=self.repository_root,
            provider=self.provider.name,
            iterations=iterations,
            allowed_files=self.allowed_files,
            allowed_validation_commands=self.allowed_validation_commands,
            applied_files=sorted(applied_files),
            tool_results=tool_results,
            validation_results=validation_results,
            diff_path=diff_path,
            failure_reason=failure_reason,
            warnings=warnings,
        )
        self.run_store.append_event(
            "implementation_finished",
            {"status": str(report.status), "applied_files": report.applied_files},
        )
        return report

    def _validate_inputs(self) -> None:
        self.config.assert_working_path_allowed(self.repository_root)
        if self.repository_map.repository_root.resolve() != self.repository_root:
            raise ImplementationError("repository map root must match configured repository root")
        known_paths = {record.path for record in self.repository_map.files}
        scoped_paths = {
            reference.value
            for reference in self.task_contract.scoped_repository_context
            if reference.in_repository_map is not False
        }
        if not self.allowed_files:
            raise ImplementationError("at least one allowed file is required")
        for path in self.allowed_files:
            self._resolve_allowed_file(path)
            if path not in scoped_paths:
                raise ImplementationError(f"allowed file is outside task scope: {path}")
            if path not in known_paths:
                raise ImplementationError(f"allowed file is missing from repository map: {path}")
        for command_name in self.allowed_validation_commands:
            if command_name not in self.config.commands:
                raise ImplementationError(
                    f"allowed validation command is not configured: {command_name}"
                )

    def _apply_tool_call(self, tool_call: ToolCall) -> ToolResult:
        try:
            path = self._resolve_allowed_file(tool_call.path)
        except ImplementationError as exc:
            return ToolResult(
                tool=tool_call.tool,
                path=tool_call.path,
                status="failed",
                message=str(exc),
            )
        if tool_call.tool == ToolName.READ_FILE:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                return ToolResult(
                    tool=tool_call.tool,
                    path=tool_call.path,
                    status="failed",
                    message=f"could not read file: {exc}",
                )
            artifact = (
                self.run_store.run_dir
                / "implementation"
                / "read-files"
                / tool_call.path.replace("/", "__")
            )
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(text, encoding="utf-8")
            return ToolResult(
                tool=tool_call.tool,
                path=tool_call.path,
                status="read",
                message=f"wrote read artifact: {artifact}",
            )
        if tool_call.tool == ToolName.REPLACE_TEXT:
            return self._replace_text(path, tool_call)
        return ToolResult(
            tool=tool_call.tool,
            path=tool_call.path,
            status="failed",
            message=f"unsupported tool: {tool_call.tool}",
        )

    def _replace_text(self, path: Path, tool_call: ToolCall) -> ToolResult:
        if tool_call.old is None or tool_call.new is None:
            return ToolResult(
                tool=tool_call.tool,
                path=tool_call.path,
                status="failed",
                message="replace_text requires old and new text",
            )
        text = path.read_text(encoding="utf-8")
        occurrences = text.count(tool_call.old)
        if occurrences != 1:
            return ToolResult(
                tool=tool_call.tool,
                path=tool_call.path,
                status="failed",
                message=f"replace_text expected exactly one match, found {occurrences}",
            )
        path.write_text(text.replace(tool_call.old, tool_call.new, 1), encoding="utf-8")
        return ToolResult(
            tool=tool_call.tool,
            path=tool_call.path,
            status="applied",
            message="replacement applied",
        )

    def _resolve_allowed_file(self, relative_path: str) -> Path:
        if relative_path not in self.allowed_files:
            raise ImplementationError(f"file is not explicitly allowed: {relative_path}")
        path = (self.repository_root / relative_path).resolve()
        if not path.is_relative_to(self.repository_root):
            raise ImplementationError(f"file resolves outside repository: {relative_path}")
        self.config.assert_working_path_allowed(path)
        if not path.exists() or not path.is_file():
            raise ImplementationError(f"allowed file does not exist: {relative_path}")
        return path

    def _prompt_text(self) -> str:
        return json.dumps(
            {
                "task_contract": self.task_contract.model_dump(mode="json"),
                "repository_map_summary": {
                    "repository_root": str(self.repository_map.repository_root),
                    "files": [record.path for record in self.repository_map.files],
                    "commands": [command.label for command in self.repository_map.commands],
                },
                "allowed_files": self.allowed_files,
                "allowed_validation_commands": self.allowed_validation_commands,
                "tool_protocol": [
                    {"tool": "read_file", "path": "<allowed repository-relative path>"},
                    {
                        "tool": "replace_text",
                        "path": "<allowed repository-relative path>",
                        "old": "<exact old text>",
                        "new": "<replacement text>",
                    },
                ],
            },
            sort_keys=True,
        )

    def _write_diff(self) -> Path:
        output = self.run_store.run_dir / "implementation" / "diff.patch"
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "-C", str(self.repository_root), "diff", "--", *self.allowed_files],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        output.write_text(result.stdout, encoding="utf-8")
        return output

    @staticmethod
    def _write_json(path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
