from __future__ import annotations

from pathlib import Path

from rtl_agent.mvp_demo.synthesis import render_debug_summary
from rtl_agent.mvp_demo_models import MvpDemoSummary


def write_demo_summary(summary: MvpDemoSummary, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")


def render_demo_markdown(summary: MvpDemoSummary, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_debug_summary(summary), encoding="utf-8")
