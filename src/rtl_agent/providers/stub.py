from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from rtl_agent.implementation_models import ProviderRequest, ProviderResponse
from rtl_agent.providers.base import ProviderError


class StubProviderPlan(BaseModel):
    responses: list[ProviderResponse] = Field(min_length=1)


class StubProvider:
    name = "stub"

    def __init__(self, plan_path: Path) -> None:
        self.plan_path = plan_path.resolve()
        try:
            self.plan = StubProviderPlan.model_validate_json(
                self.plan_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise ProviderError(f"invalid stub provider plan: {self.plan_path}") from exc

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        index = request.iteration - 1
        if index >= len(self.plan.responses):
            return ProviderResponse(
                message="stub provider has no response for this iteration",
                stop=True,
            )
        return self.plan.responses[index]
