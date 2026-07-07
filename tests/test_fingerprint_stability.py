from __future__ import annotations

from pathlib import Path

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_fingerprint import (
    compare_fingerprint_reports,
    fingerprint_run,
)
from rtl_agent.failure_intelligence_run import run_failure_intelligence

CORE_SV = """module core (
    input  logic       clk,
    output logic [7:0] hold,
    output logic [7:0] flag
);
    assign hold = 8'h00;
    assign flag = 8'h00;
endmodule
"""


def _vcd_header() -> str:
    return (
        "$timescale 1ns $end\n"
        "$scope module tb $end\n$scope module core $end\n"
        "$var reg 8 ! hold [7:0] $end\n"
        '$var reg 8 " flag [7:0] $end\n'
        "$upscope $end\n$upscope $end\n$enddefinitions $end\n"
        '$dumpvars\nb00000000 !\nb00000000 "\n$end\n'
    )


def _clean(path: Path, *, load_at: int, end_at: int) -> Path:
    body = _vcd_header() + f'#{load_at}\nb10101010 !\nb10101010 "\n#{end_at}\n'
    path.write_text(body, encoding="utf-8")
    return path


def _failing(
    path: Path,
    *,
    signal: str,
    fault_at: int,
    load_at: int,
    end_at: int,
    xz: bool = True,
) -> Path:
    ident = "!" if signal == "hold" else '"'
    value = "bxxxxxxxx" if xz else "b01010101"
    body = _vcd_header() + f'#{load_at}\nb10101010 !\nb10101010 "\n'
    body += f"#{fault_at}\n{value} {ident}\n#{end_at}\n"
    path.write_text(body, encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "core.sv").write_text(CORE_SV, encoding="utf-8")
    return rtl


def _run(tmp_path: Path, rtl: Path, failing: Path, passing: Path, name: str, ft: int):  # type: ignore[no-untyped-def]
    store = RunStore(tmp_path / "runs", run_id=name)
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=failing,
        passing_vcd=passing,
        repository_root=rtl,
        failure_time=ft,
        before=15,
        after=15,
    )
    return fingerprint_run(store.run_dir)


def test_canonical_stable_across_stimulus_length(tmp_path: Path) -> None:
    rtl = _repo(tmp_path)
    # Shared passing reference (the payload loads at t=30 and holds).
    passing = _clean(tmp_path / "pass.vcd", load_at=30, end_at=120)
    # Two manifestations of the SAME failure: `hold` diverges to x, but at
    # different absolute times so the comparison window captures a different
    # amount of surrounding activity (a shorter vs a longer reproduction). The
    # timing and windowed transition counts differ; the failure identity does not.
    short = _failing(tmp_path / "short.vcd", signal="hold", fault_at=40, load_at=30, end_at=60)
    long = _failing(tmp_path / "long.vcd", signal="hold", fault_at=90, load_at=30, end_at=120)
    fp_short = _run(tmp_path, rtl, short, passing, "short", 40)
    fp_long = _run(tmp_path, rtl, long, passing, "long", 90)

    assert not fp_short.insufficient_evidence and not fp_long.insufficient_evidence
    # The canonical fingerprint is stable across the benign variation...
    assert fp_short.canonical_digest
    assert fp_short.canonical_digest == fp_long.canonical_digest
    # ...even though the exact (timing-sensitive) fingerprint differs.
    assert fp_short.exact_digest != fp_long.exact_digest
    # The comparison surfaces the canonical match.
    comparison = compare_fingerprint_reports(
        fp_short, fp_long, left_path=Path("short"), right_path=Path("long")
    )
    assert comparison.canonical_match is True


def test_canonical_differs_for_different_failing_signal(tmp_path: Path) -> None:
    rtl = _repo(tmp_path)
    passing = _clean(tmp_path / "pass.vcd", load_at=30, end_at=80)
    on_hold = _failing(tmp_path / "hold.vcd", signal="hold", fault_at=40, load_at=30, end_at=80)
    on_flag = _failing(tmp_path / "flag.vcd", signal="flag", fault_at=40, load_at=30, end_at=80)
    fp_hold = _run(tmp_path, rtl, on_hold, passing, "hold", 40)
    fp_flag = _run(tmp_path, rtl, on_flag, passing, "flag", 40)
    # A different failure locus is a different failure: distinct canonical digests.
    assert fp_hold.canonical_digest != fp_flag.canonical_digest
    comparison = compare_fingerprint_reports(
        fp_hold, fp_flag, left_path=Path("h"), right_path=Path("f")
    )
    assert comparison.canonical_match is False


def test_canonical_distinguishes_xz_from_defined_corruption(tmp_path: Path) -> None:
    rtl = _repo(tmp_path)
    passing = _clean(tmp_path / "pass.vcd", load_at=30, end_at=80)
    xz = _failing(tmp_path / "xz.vcd", signal="hold", fault_at=40, load_at=30, end_at=80, xz=True)
    defined = _failing(
        tmp_path / "def.vcd", signal="hold", fault_at=40, load_at=30, end_at=80, xz=False
    )
    fp_xz = _run(tmp_path, rtl, xz, passing, "xz", 40)
    fp_def = _run(tmp_path, rtl, defined, passing, "defined", 40)
    # An x/z corruption and a defined-value corruption on the same signal are
    # intentionally distinct canonical failures.
    assert fp_xz.canonical_digest != fp_def.canonical_digest


def test_canonical_is_deterministic(tmp_path: Path) -> None:
    rtl = _repo(tmp_path)
    passing = _clean(tmp_path / "pass.vcd", load_at=30, end_at=80)
    failing = _failing(tmp_path / "f.vcd", signal="hold", fault_at=40, load_at=30, end_at=80)
    a = _run(tmp_path, rtl, failing, passing, "a", 40)
    b = _run(tmp_path, rtl, failing, passing, "b", 40)
    assert a.canonical_digest == b.canonical_digest
    assert a.canonical_divergence == b.canonical_divergence
