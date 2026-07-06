from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.stimulus import (
    StimulusError,
    materialize_stimulus,
    parse_stimulus,
    stimulus_digest,
    subset_by_ids,
    to_hex_program,
)
from rtl_agent.stimulus_models import StimulusItem, StructuredStimulus


def _write(path: Path, items: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps({"schema_version": 1, "items": items}), encoding="utf-8")
    return path


def test_valid_structured_stimulus_parses(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "s.json",
        [
            {"id": "a", "index": 0, "kind": "idle", "payload": {}},
            {"id": "b", "index": 1, "kind": "send", "payload": {"data": "AA"}},
        ],
    )
    stimulus = parse_stimulus(path)
    assert [item.id for item in stimulus.items] == ["a", "b"]
    assert stimulus.items[1].kind == "send"


def test_duplicate_item_ids_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "s.json",
        [
            {"id": "a", "index": 0, "kind": "idle", "payload": {}},
            {"id": "a", "index": 1, "kind": "idle", "payload": {}},
        ],
    )
    with pytest.raises(StimulusError, match="duplicate stimulus item id"):
        parse_stimulus(path)


def test_malformed_item_rejected(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"schema_version": 1, "items": [{"id": "a", "kind": "idle"}]}),
        encoding="utf-8",
    )
    with pytest.raises(StimulusError):
        parse_stimulus(path)


def test_empty_stimulus_is_valid(tmp_path: Path) -> None:
    path = _write(tmp_path / "s.json", [])
    stimulus = parse_stimulus(path)
    assert stimulus.items == []


def test_deterministic_semantic_digest_excludes_metadata() -> None:
    a = StructuredStimulus(
        items=[
            StimulusItem(id="x", index=0, kind="send", payload={"data": "AA"}, metadata={"n": 1})
        ]
    )
    b = StructuredStimulus(
        items=[
            StimulusItem(id="x", index=0, kind="send", payload={"data": "AA"}, metadata={"n": 9})
        ]
    )
    c = StructuredStimulus(
        items=[StimulusItem(id="x", index=0, kind="send", payload={"data": "BB"})]
    )
    assert stimulus_digest(a) == stimulus_digest(b)
    assert stimulus_digest(a) != stimulus_digest(c)


def test_subset_preserves_order_and_renumbers(tmp_path: Path) -> None:
    stimulus = StructuredStimulus(
        items=[
            StimulusItem(id="a", index=0, kind="idle"),
            StimulusItem(id="b", index=1, kind="send", payload={"data": "AA"}),
            StimulusItem(id="c", index=2, kind="stall"),
        ]
    )
    reduced = subset_by_ids(stimulus, ["c", "a"])
    assert [item.id for item in reduced.items] == ["a", "c"]
    assert [item.index for item in reduced.items] == [0, 1]


def test_hex_program_encoding() -> None:
    stimulus = StructuredStimulus(
        items=[
            StimulusItem(id="a", index=0, kind="idle"),
            StimulusItem(id="b", index=1, kind="send", payload={"data": "AA"}),
            StimulusItem(id="c", index=2, kind="stall"),
        ]
    )
    assert to_hex_program(stimulus) == ["0000", "10aa", "2000"]


def test_materialize_writes_json_and_mem(tmp_path: Path) -> None:
    stimulus = StructuredStimulus(
        items=[StimulusItem(id="b", index=0, kind="send", payload={"data": "AA"})]
    )
    json_path, mem_path = materialize_stimulus(stimulus, tmp_path)
    assert json_path == tmp_path / "sim" / "stimulus.json"
    assert mem_path.read_text(encoding="utf-8").strip() == "10aa"
