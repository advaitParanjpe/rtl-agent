from __future__ import annotations

from pydantic import BaseModel, Field

INTERVENTION_RANKING_SCHEMA_VERSION = 1


class RankingFactor(BaseModel):
    factor: str
    points: int


class InterventionRanking(BaseModel):
    intervention_id: str
    template_kind: str | None = None
    confidence: str | None = None
    rank: int | None = None
    score: int = 0
    ranked: bool = False
    observed_effect: str = "unknown"
    result_cluster_id: str | None = None
    result_cluster_size: int | None = None
    factors: list[RankingFactor] = Field(default_factory=list)
    explanation: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    unranked_reason: str | None = None
