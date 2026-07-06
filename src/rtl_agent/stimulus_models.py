from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

STRUCTURED_STIMULUS_SCHEMA_VERSION = 1


class StimulusItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    index: int = Field(ge=0)
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    # Metadata is preserved for provenance but excluded from semantic identity.
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredStimulus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = STRUCTURED_STIMULUS_SCHEMA_VERSION
    items: list[StimulusItem] = Field(default_factory=list)
