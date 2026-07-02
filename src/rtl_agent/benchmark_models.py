from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BENCHMARK_MANIFEST_SCHEMA_VERSION = 1
BENCHMARK_REPORT_SCHEMA_VERSION = 1


class BenchmarkStepKind(StrEnum):
    NAMED_COMMAND = "named_command"


class BenchmarkStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class BenchmarkResources(BaseModel):
    max_cases: int = Field(gt=0)
    max_steps_per_case: int = Field(gt=0)
    max_step_timeout_seconds: int = Field(gt=0)


class BenchmarkStep(BaseModel):
    step_id: str = Field(min_length=1)
    kind: BenchmarkStepKind = BenchmarkStepKind.NAMED_COMMAND
    config: Path
    command: str = Field(min_length=1)
    expected_status: BenchmarkStatus
    timeout_seconds: int | None = Field(default=None, gt=0)

    @field_validator("step_id", "command")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("benchmark text fields must not be blank")
        return value


class BenchmarkCase(BaseModel):
    case_id: str = Field(min_length=1)
    description: str | None = None
    steps: list[BenchmarkStep] = Field(min_length=1)

    @field_validator("case_id")
    @classmethod
    def reject_blank_case_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case_id must not be blank")
        return value


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = BENCHMARK_MANIFEST_SCHEMA_VERSION
    name: str = Field(min_length=1)
    run_artifact_dir: Path
    resources: BenchmarkResources
    cases: list[BenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> BenchmarkManifest:
        if self.schema_version != BENCHMARK_MANIFEST_SCHEMA_VERSION:
            raise ValueError("only benchmark manifest schema_version 1 is supported")
        if len(self.cases) > self.resources.max_cases:
            raise ValueError("manifest case count exceeds resources.max_cases")
        for case in self.cases:
            if len(case.steps) > self.resources.max_steps_per_case:
                raise ValueError(f"case {case.case_id} exceeds resources.max_steps_per_case")
            for step in case.steps:
                if (
                    step.timeout_seconds is not None
                    and step.timeout_seconds > self.resources.max_step_timeout_seconds
                ):
                    raise ValueError(
                        f"step {case.case_id}/{step.step_id} exceeds "
                        "resources.max_step_timeout_seconds"
                    )
        return self


class BenchmarkStepResult(BaseModel):
    case_id: str
    step_id: str
    kind: BenchmarkStepKind
    command_name: str
    expected_status: BenchmarkStatus
    observed_status: BenchmarkStatus
    expectation_met: bool
    duration_seconds: float = Field(ge=0)
    command_result_path: Path | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    failure_summary: str | None = None


class BenchmarkCaseResult(BaseModel):
    case_id: str
    status: BenchmarkStatus
    expectation_met: bool
    step_results: list[BenchmarkStepResult] = Field(default_factory=list)


class BenchmarkReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: int = BENCHMARK_REPORT_SCHEMA_VERSION
    manifest_path: Path
    manifest_name: str
    run_id: str
    run_dir: Path
    status: BenchmarkStatus
    cases_total: int
    cases_passed: int
    cases_failed: int
    cases_timeout: int
    cases_infrastructure_error: int
    case_results: list[BenchmarkCaseResult] = Field(default_factory=list)
    summary: str
