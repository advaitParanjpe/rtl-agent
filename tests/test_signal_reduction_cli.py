from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app

FIXTURE_VCD = "examples/waveforms/failure.vcd"


def make_slice(tmp_path: Path) -> Path:
    slice_path = tmp_path / "slice.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "extract-waveform-window",
            "--vcd",
            FIXTURE_VCD,
            "--failure-time",
            "40",
            "--before",
            "15",
            "--after",
            "5",
            "--output",
            str(slice_path),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return slice_path


def test_cli_reduce_signals_writes_reports(tmp_path: Path) -> None:
    slice_path = make_slice(tmp_path)
    output = tmp_path / "reduction.json"
    reduced = tmp_path / "reduced.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "reduce-signals",
            "--waveform-slice",
            str(slice_path),
            "--assertion-signal",
            "top.dut.valid",
            "--reduced-slice-output",
            str(reduced),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert report["retained_signals"][0]["name"] == "top.dut.valid"
    reduced_slice = json.loads(reduced.read_text(encoding="utf-8"))
    assert reduced_slice["schema_version"] == 1
    assert "top.dut.valid" in {s["name"] for s in reduced_slice["selected_signals"]}


def test_cli_reduce_signals_rejects_missing_slice(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "reduce-signals",
            "--waveform-slice",
            str(tmp_path / "missing.json"),
            "--reduced-slice-output",
            str(tmp_path / "reduced.json"),
            "--output",
            str(tmp_path / "reduction.json"),
        ],
    )

    assert result.exit_code == 2
    assert "could not load waveform slice" in result.stderr
