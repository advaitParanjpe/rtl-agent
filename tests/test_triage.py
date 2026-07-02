from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.models import CommandResult, CommandStatus, utc_now
from rtl_agent.triage import TriageError, triage_command_result, write_triage_report


def write_command_result(
    tmp_path: Path,
    stdout: str = "",
    stderr: str = "",
    status: CommandStatus = CommandStatus.FAILED,
    exit_code: int | None = 1,
) -> Path:
    cwd = tmp_path / "repo"
    cwd.mkdir(exist_ok=True)
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    now = utc_now()
    result = CommandResult(
        command_id="sim-1",
        command_name="sim",
        argv=["sim"],
        cwd=cwd,
        status=status,
        started_at=now,
        ended_at=now,
        duration_seconds=0,
        exit_code=exit_code,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result.model_dump(mode="json")), encoding="utf-8")
    return path


def test_triage_extracts_assertions_waveforms_and_context(tmp_path: Path) -> None:
    (tmp_path / "repo" / "waves").mkdir(parents=True)
    (tmp_path / "repo" / "waves" / "dump.vcd").write_text("$date\n", encoding="utf-8")
    result_path = write_command_result(
        tmp_path,
        stdout=(
            "Verilator simulation start\n"
            "ASSERTION FAILED property p_valid at time 120 ns\n"
            "Dumped waveform waves/dump.vcd\n"
        ),
        stderr="UVM_ERROR scoreboard mismatch at time 121 ns; see missing.fst\n",
    )

    report = triage_command_result(result_path)

    assert "p_valid" in [item.signal_or_label for item in report.assertion_failures]
    assert "120 ns" in [item.time_context for item in report.assertion_failures]
    assert [item.path for item in report.waveform_references] == [
        "missing.fst",
        "waves/dump.vcd",
    ]
    assert [item.exists for item in report.waveform_references] == [False, True]
    assert "referenced waveform file is missing: missing.fst" in report.warnings
    assert any(item.category == "verilator" for item in report.simulator_context)
    assert len(report.bounded_evidence) <= 24


def test_triage_is_bounded_for_large_logs(tmp_path: Path) -> None:
    result_path = write_command_result(
        tmp_path,
        stdout="\n".join(
            f"ASSERTION FAILED property p_{index} at time {index} ns" for index in range(300)
        ),
    )

    report = triage_command_result(result_path)

    assert len(report.assertion_failures) == 24
    assert len(report.bounded_evidence) == 24


def test_triage_writes_stable_json(tmp_path: Path) -> None:
    result_path = write_command_result(
        tmp_path, stderr="assertion failed property p at time 1 ns\n"
    )
    report = triage_command_result(result_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_triage_report(report, first)
    write_triage_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_triage_rejects_malformed_result(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")

    with pytest.raises(TriageError, match="could not load command result"):
        triage_command_result(bad)
