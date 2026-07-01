from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from rtl_agent.models import CommandResult, RunEvent, RunMetadata, utc_now


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"object is not JSON serializable: {type(value)!r}")


class RunStore:
    def __init__(self, root: Path, run_id: str | None = None) -> None:
        self.root = root.resolve()
        self.run_id = run_id or utc_now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        self.run_dir = self.root / self.run_id
        self.commands_dir = self.run_dir / "commands"

    def create(self) -> None:
        self.commands_dir.mkdir(parents=True, exist_ok=False)
        metadata = RunMetadata(run_id=self.run_id, created_at=utc_now())
        self._write_json(self.run_dir / "run.json", metadata.model_dump(mode="json"))
        self.append_event("run_created", {"run_id": self.run_id})

    def append_event(self, event: str, data: dict[str, object] | None = None) -> None:
        payload = RunEvent(timestamp=utc_now(), event=event, data=data or {})
        with (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload.model_dump(mode="json"), sort_keys=True) + "\n")

    def command_dir(self, command_id: str) -> Path:
        path = self.commands_dir / command_id
        path.mkdir(parents=True, exist_ok=False)
        return path

    def write_command_result(self, command_dir: Path, result: CommandResult) -> Path:
        result_path = command_dir / "result.json"
        self._write_json(result_path, result.model_dump(mode="json"))
        self.append_event(
            "command_finished",
            {
                "command_id": result.command_id,
                "command_name": result.command_name,
                "status": str(result.status),
                "exit_code": result.exit_code,
            },
        )
        return result_path

    @staticmethod
    def _write_json(path: Path, data: dict[str, object]) -> None:
        path.write_text(
            json.dumps(data, default=_json_default, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
