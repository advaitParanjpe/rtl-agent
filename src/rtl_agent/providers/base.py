from __future__ import annotations

from typing import Protocol

from rtl_agent.implementation_models import ProviderRequest, ProviderResponse


class ProviderError(RuntimeError):
    pass


class ModelProvider(Protocol):
    name: str

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return one structured response for a bounded implementation iteration."""
