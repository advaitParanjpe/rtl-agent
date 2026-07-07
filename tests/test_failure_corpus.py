from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.config import load_config
from rtl_agent.stimulus import parse_stimulus, to_hex_program

CORPUS = Path("examples/failure-corpus")
MANIFEST = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
EXAMPLES = MANIFEST["examples"]
IDS = [e["name"] for e in EXAMPLES]


def test_corpus_has_multiple_distinct_failure_classes() -> None:
    assert len(EXAMPLES) >= 3, "the corpus must contain at least three examples"
    classes = [e["failure_class"] for e in EXAMPLES]
    assert len(set(classes)) == len(classes), "each example must be a distinct failure class"
    assert len({e["name"] for e in EXAMPLES}) == len(EXAMPLES)


@pytest.mark.parametrize("example", EXAMPLES, ids=IDS)
def test_example_files_present(example: dict[str, str]) -> None:
    d = CORPUS / example["name"]
    module = example["module"]
    for relative in (
        f"rtl/{example['rtl_file']}",
        f"tb/{example['tb_file']}",
        "sim/run.sh",
        "sim/stimulus.mem",
        "rtl-agent.yaml",
        example["stimulus"],
    ):
        assert (d / relative).is_file(), f"{example['name']} missing {relative}"
    assert example["rtl_file"] == f"{module}.sv"
    assert example["tb_file"] == f"{module}_tb.sv"
    assert example["allowed_file"] == f"rtl/{module}.sv"


@pytest.mark.parametrize("example", EXAMPLES, ids=IDS)
def test_example_rtl_seeds_a_compile_time_fault(example: dict[str, str]) -> None:
    rtl = (CORPUS / example["name"] / "rtl" / example["rtl_file"]).read_text(encoding="utf-8")
    # The failure is a compile-time seeded fault, not an always-on bug.
    assert "`ifdef INJECT_FAULT" in rtl
    assert "'x" in rtl, "the seeded fault should corrupt a signal to x"


@pytest.mark.parametrize("example", EXAMPLES, ids=IDS)
def test_example_stimulus_parses_and_matches_mem(example: dict[str, str]) -> None:
    d = CORPUS / example["name"]
    stimulus = parse_stimulus(d / example["stimulus"])
    assert stimulus.items, f"{example['name']}: empty stimulus"
    # The checked-in hex program matches the structured stimulus.
    committed = (d / "sim" / "stimulus.mem").read_text(encoding="utf-8").split()
    assert committed == to_hex_program(stimulus), f"{example['name']}: stimulus.mem out of sync"


@pytest.mark.parametrize("example", EXAMPLES, ids=IDS)
def test_example_config_exposes_named_command(example: dict[str, str]) -> None:
    config = load_config(CORPUS / example["name"] / "rtl-agent.yaml")
    assert example["command"] in config.commands, example["name"]
    assert str(config.repository_path) == "rtl"
