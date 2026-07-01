from __future__ import annotations

import json
from pathlib import Path

from rtl_agent.artifacts import RunStore


def test_run_store_creates_metadata_and_events(tmp_path: Path) -> None:
    store = RunStore(tmp_path, run_id="run-1")
    store.create()
    store.append_event("custom", {"ok": True})

    assert (tmp_path / "run-1" / "run.json").exists()
    events = (tmp_path / "run-1" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 2
    assert json.loads(events[1])["event"] == "custom"
