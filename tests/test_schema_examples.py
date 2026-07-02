from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from rtl_agent.benchmark_models import BenchmarkReport
from rtl_agent.evidence_bundle_models import EvidenceBundleReport
from rtl_agent.implementation_models import ImplementationReport
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.review_models import ReviewReport
from rtl_agent.task_contract import TaskContract
from rtl_agent.triage_models import TriageReport
from rtl_agent.verification_strength_models import VerificationStrengthReport

SCHEMA_EXAMPLES = Path("examples/schema-artifacts")

EXAMPLES: dict[str, type[BaseModel]] = {
    "repository-map.json": RepositoryMap,
    "task-contract.json": TaskContract,
    "implementation-report.json": ImplementationReport,
    "review-report.json": ReviewReport,
    "triage-report.json": TriageReport,
    "verification-strength-report.json": VerificationStrengthReport,
    "benchmark-report.json": BenchmarkReport,
    "evidence-bundle-report.json": EvidenceBundleReport,
}

VOLATILE_KEYS = {
    "created_at",
    "discovered_at",
    "duration_seconds",
    "ended_at",
    "run_id",
    "sha256",
    "started_at",
}


def test_all_schema_examples_are_covered() -> None:
    discovered = {path.name for path in SCHEMA_EXAMPLES.glob("*.json")}

    assert discovered == set(EXAMPLES)


def test_schema_examples_validate_and_serialize_through_current_models() -> None:
    for filename, model in EXAMPLES.items():
        raw = (SCHEMA_EXAMPLES / filename).read_text(encoding="utf-8")

        artifact = model.model_validate_json(raw)
        serialized = artifact.model_dump(mode="json")

        assert serialized["schema_version"] == 1
        assert _without_volatile_values(serialized)


def test_schema_examples_are_compact() -> None:
    for path in SCHEMA_EXAMPLES.glob("*.json"):
        assert path.stat().st_size < 12_000


def test_schema_examples_do_not_embed_large_artifact_content() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in SCHEMA_EXAMPLES.glob("*.json")
    )

    forbidden_fragments = [".vcd", ".fst", ".fsdb", "BEGIN RSA", "PRIVATE KEY"]
    assert not any(fragment in combined for fragment in forbidden_fragments)


def _without_volatile_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_volatile_values(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_without_volatile_values(item) for item in value]
    return value
