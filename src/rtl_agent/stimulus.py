from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.stimulus_models import (
    STRUCTURED_STIMULUS_SCHEMA_VERSION,
    StimulusItem,
    StructuredStimulus,
)

# Fixture-facing action opcodes for the supported structured stimulus format.
# The reduction harness itself never interprets these; only materialization for
# the compact AXI-style testbench does.
_OPCODES = {"idle": 0x0, "send": 0x1, "stall": 0x2}


class StimulusError(RuntimeError):
    pass


def parse_stimulus(path: Path) -> StructuredStimulus:
    """Load and validate a structured stimulus JSON file."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StimulusError(f"stimulus is not readable JSON: {path} ({exc})") from exc
    return load_stimulus(raw, source=str(path))


def load_stimulus(raw: object, *, source: str = "<stimulus>") -> StructuredStimulus:
    if not isinstance(raw, dict):
        raise StimulusError(f"stimulus is not a JSON object: {source}")
    version = raw.get("schema_version")
    if version is not None and version != STRUCTURED_STIMULUS_SCHEMA_VERSION:
        raise StimulusError(
            f"unsupported stimulus schema version: {version} "
            f"(expected {STRUCTURED_STIMULUS_SCHEMA_VERSION})"
        )
    try:
        stimulus = StructuredStimulus.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise StimulusError(f"malformed structured stimulus: {source} ({exc})") from exc
    _validate_items(stimulus)
    return stimulus


def _validate_items(stimulus: StructuredStimulus) -> None:
    seen: set[str] = set()
    for item in stimulus.items:
        if not item.id:
            raise StimulusError("stimulus item has an empty id")
        if item.id in seen:
            raise StimulusError(f"duplicate stimulus item id: {item.id}")
        seen.add(item.id)
        if not item.kind:
            raise StimulusError(f"stimulus item has an empty kind: {item.id}")


def stimulus_digest(stimulus: StructuredStimulus) -> str:
    """Deterministic semantic digest over the ordered items.

    Identity is the ordered sequence of (kind, payload) — the content that
    determines the materialized simulation. Item ids, indices, and metadata are
    excluded, so two candidates that produce the same stimulus program share a
    digest (and therefore a cached evaluation).
    """

    payload = [{"kind": item.kind, "payload": item.payload} for item in stimulus.items]
    return sha256((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")).hexdigest()


def subset_by_ids(stimulus: StructuredStimulus, retained_ids: list[str]) -> StructuredStimulus:
    """Return the ordered subset of items whose ids are in ``retained_ids``.

    Relative order of retained items is preserved and indices are renumbered so
    the result is a fresh, contiguous ordered stimulus.
    """

    keep = set(retained_ids)
    items = [item for item in stimulus.items if item.id in keep]
    return StructuredStimulus(
        schema_version=stimulus.schema_version,
        items=[
            StimulusItem(
                id=item.id,
                index=position,
                kind=item.kind,
                payload=dict(item.payload),
                metadata=dict(item.metadata),
            )
            for position, item in enumerate(items)
        ],
    )


def write_stimulus(stimulus: StructuredStimulus, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(stimulus.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def to_hex_program(stimulus: StructuredStimulus) -> list[str]:
    """Encode the structured stimulus as one 16-bit hex opcode word per item."""

    words: list[str] = []
    for item in stimulus.items:
        opcode = _OPCODES.get(item.kind, 0x0)
        data = 0
        if item.kind == "send":
            raw = str(item.payload.get("data", "0"))
            try:
                data = int(raw, 16) & 0xFF
            except ValueError:
                data = 0
        words.append(f"{(opcode << 12) | data:04x}")
    return words


def materialize_stimulus(
    stimulus: StructuredStimulus, worktree: Path, *, relative_dir: str = "sim"
) -> tuple[Path, Path]:
    """Write the candidate stimulus (JSON) and its hex program into the worktree.

    Returns the (json_path, mem_path) written under ``worktree/<relative_dir>``.
    """

    target_dir = (worktree / relative_dir).resolve()
    if not target_dir.is_relative_to(worktree.resolve()):
        raise StimulusError("stimulus target directory escapes the worktree")
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "stimulus.json"
    mem_path = target_dir / "stimulus.mem"
    write_stimulus(stimulus, json_path)
    program = to_hex_program(stimulus)
    mem_path.write_text(("\n".join(program) + "\n") if program else "", encoding="utf-8")
    return json_path, mem_path
