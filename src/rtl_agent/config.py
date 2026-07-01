from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class ExecutionConfig(BaseModel):
    timeout_seconds: int = Field(default=300, gt=0)
    max_output_bytes: int = Field(default=10_485_760, gt=0)


class CommandConfig(BaseModel):
    argv: list[str] = Field(min_length=1)
    cwd: Path = Path(".")
    timeout_seconds: int | None = Field(default=None, gt=0)

    @field_validator("argv")
    @classmethod
    def reject_empty_args(cls, value: list[str]) -> list[str]:
        if any(arg == "" for arg in value):
            raise ValueError("command argv entries must be non-empty")
        return value


class AgentConfig(BaseModel):
    schema_version: int = 1
    repository_path: Path
    run_artifact_dir: Path
    allowed_working_paths: list[Path] = Field(min_length=1)
    protected_paths: list[Path] = Field(default_factory=list)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    commands: dict[str, CommandConfig] = Field(default_factory=dict)
    config_path: Path | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_schema_version(self) -> AgentConfig:
        if self.schema_version != 1:
            raise ValueError("only schema_version 1 is supported")
        return self

    def base_dir(self) -> Path:
        if self.config_path is None:
            return Path.cwd()
        return self.config_path.parent

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path.resolve()
        return (self.base_dir() / path).resolve()

    @property
    def repository_root(self) -> Path:
        return self.resolve_path(self.repository_path)

    @property
    def run_root(self) -> Path:
        return self.resolve_path(self.run_artifact_dir)

    def command_cwd(self, command: CommandConfig) -> Path:
        return self.resolve_path(command.cwd)

    def assert_working_path_allowed(self, path: Path) -> None:
        resolved = path.resolve()
        allowed = [self.resolve_path(item) for item in self.allowed_working_paths]
        if not any(resolved == item or resolved.is_relative_to(item) for item in allowed):
            raise ValueError(f"path is outside allowed working paths: {resolved}")

        protected = [self.resolve_path(item) for item in self.protected_paths]
        if any(resolved == item or resolved.is_relative_to(item) for item in protected):
            raise ValueError(f"path is under protected path: {resolved}")


def load_config(path: Path) -> AgentConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML config: {path}") from exc

    if not isinstance(raw, dict):
        raise ValueError("config root must be a mapping")

    data: dict[str, Any] = raw
    config = AgentConfig.model_validate(data)
    config.config_path = path.resolve()
    return config
