from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtl_agent.cli import app

FIXTURE_VCD = "examples/waveforms/failure.vcd"


def extract(tmp_path: Path, name: str, vcd: str) -> Path:
    out = tmp_path / f"{name}.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "extract-waveform-window",
            "--vcd",
            vcd,
            "--failure-time",
            "40",
            "--before",
            "15",
            "--after",
            "15",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return out


def make_passing_vcd(tmp_path: Path) -> str:
    # Same signals/timescale as the fixture, but state stays stable and valid stays high.
    vcd = tmp_path / "passing.vcd"
    vcd.write_text(
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! clk $end\n"
        "$var reg 8 @ data [7:0] $end\n"
        "$scope module dut $end\n"
        "$var reg 1 % valid $end\n"
        "$var wire 4 & state [3:0] $end\n"
        "$upscope $end\n$upscope $end\n$enddefinitions $end\n"
        "$dumpvars\n0!\nb00000000 @\n1%\nb0011 &\n$end\n"
        "#30\n1%\nb0011 &\n#40\nb10101010 @\n#50\n1%\nb0011 &\n",
        encoding="utf-8",
    )
    return str(vcd)


def test_cli_compare_waveforms_writes_report(tmp_path: Path) -> None:
    failing = extract(tmp_path, "failing", FIXTURE_VCD)
    passing = extract(tmp_path, "passing", make_passing_vcd(tmp_path))
    output = tmp_path / "comparison.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "compare-waveforms",
            "--failing-slice",
            str(failing),
            "--passing-slice",
            str(passing),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert report["time_basis"]["kind"] == "shared_ticks"
    diverging = {signal["name"] for signal in report["diverging_signals"]}
    assert "top.dut.state" in diverging


def test_cli_compare_waveforms_rejects_missing_slice(tmp_path: Path) -> None:
    passing = extract(tmp_path, "passing", FIXTURE_VCD)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "compare-waveforms",
            "--failing-slice",
            str(tmp_path / "missing.json"),
            "--passing-slice",
            str(passing),
            "--output",
            str(tmp_path / "comparison.json"),
        ],
    )

    assert result.exit_code == 2
    assert "could not load failing waveform slice" in result.stderr
