from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from rtl_agent.config import DiscoveryConfig
from rtl_agent.discovery import DiscoveryError, discover_repository, write_repository_map
from rtl_agent.discovery.build_discovery import discover_build_commands
from rtl_agent.discovery.classifier import classify_file
from rtl_agent.discovery.scanner import RepositoryScanner
from rtl_agent.discovery.sv_parser import mask_comments_and_strings, parse_systemverilog
from rtl_agent.repository_map import DeclarationKind, FileCategory


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_rtl_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "rtl"
    write(
        repo / "rtl" / "types_pkg.sv",
        """
package types_pkg;
endpackage
""",
    )
    write(
        repo / "rtl" / "axi_if.sv",
        """
interface axi_if #(parameter int WIDTH = 32) (input logic clk);
endinterface
""",
    )
    write(
        repo / "rtl" / "child.sv",
        """
module child(input logic clk);
endmodule
""",
    )
    write(
        repo / "rtl" / "top.sv",
        """
module top;
  import types_pkg::*;
  `include "defs.svh"
  child u_child (.clk(clk));
  missing_ip u_missing (.clk(clk));
endmodule
""",
    )
    write(
        repo / "tb" / "top_tb.sv",
        """
module top_tb;
  top dut();
  initial begin
    $finish;
  end
endmodule
""",
    )
    write(
        repo / "Makefile",
        """
lint:
\tverilator --lint-only rtl/top.sv
sim:
\tiverilog -g2012 -o simv rtl/top.sv tb/top_tb.sv
formal:
\tsby -f top.sby
test:
\tpytest
""",
    )
    write(repo / "README.md", "# Example RTL\n")
    return repo


def test_classifies_common_file_types() -> None:
    assert FileCategory.RTL_SOURCE in classify_file(Path("rtl/top.sv"), "module top; endmodule")
    assert FileCategory.INCLUDE in classify_file(Path("rtl/defs.svh"), "")
    assert FileCategory.BUILD_CONFIG in classify_file(Path("Makefile"), "")
    assert FileCategory.SCRIPT in classify_file(Path("scripts/run.py"), "")
    assert FileCategory.DOCUMENTATION in classify_file(Path("README.md"), "")


def test_parser_extracts_declarations_relationships_and_masks_noise() -> None:
    parsed = parse_systemverilog(
        """
// module ignored;
string s = "module also_ignored;";
package types_pkg; endpackage
interface axi_if(input logic clk); endinterface
module parent;
  import types_pkg::*;
  `include "defs.svh"
  child u_child (.clk(clk));
  if (ready) begin end
endmodule
"""
    ).info

    assert [(decl.kind, decl.name) for decl in parsed.declarations] == [
        (DeclarationKind.PACKAGE, "types_pkg"),
        (DeclarationKind.INTERFACE, "axi_if"),
        (DeclarationKind.MODULE, "parent"),
    ]
    assert parsed.includes == ["defs.svh"]
    assert parsed.imports == ["types_pkg"]
    assert parsed.instantiations == ["child"]
    assert "ignored" not in mask_comments_and_strings("// ignored\n")


def test_parser_reports_declaration_keyword_line_after_comments() -> None:
    parsed = parse_systemverilog(
        """
/*
 * Header comment
 */

module aligned;
endmodule
"""
    ).info

    assert parsed.declarations[0].name == "aligned"
    assert parsed.declarations[0].line == 6


def test_scanner_respects_exclusions_limits_binary_oversized_and_symlinks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write(repo / "rtl" / "top.sv", "module top; endmodule\n")
    write(repo / "build" / "ignored.sv", "module ignored; endmodule\n")
    write(repo / "large.sv", "x" * 40)
    (repo / "binary.sv").write_bytes(b"\x00\x01")
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "outside_link").symlink_to(outside, target_is_directory=True)

    result = RepositoryScanner(
        repo, DiscoveryConfig(max_text_file_bytes=30, exclude_patterns=["rtl/excluded*"])
    ).scan()

    assert [item.relative_path for item in result.files] == ["rtl/top.sv"]
    assert result.stats.skipped_oversized == 1
    assert result.stats.skipped_binary == 1
    assert result.stats.skipped_symlink == 1
    assert result.stats.skipped_excluded >= 1


def test_repository_discovery_hierarchy_build_guidance_and_serialization(tmp_path: Path) -> None:
    repo = make_rtl_repo(tmp_path)
    repository_map = discover_repository(repo)
    output = tmp_path / "repository-map.json"
    write_repository_map(repository_map, output)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["schema_version"] == 1
    assert [record["path"] for record in data["files"]] == sorted(
        record["path"] for record in data["files"]
    )
    assert "top" in [item["name"] for item in data["hierarchy"]["design_top_candidates"]]
    assert "top_tb" in [item["name"] for item in data["hierarchy"]["testbench_top_candidates"]]
    assert "missing_ip" in data["hierarchy"]["unresolved_instantiations"]
    assert {command["tool"] for command in data["commands"]} >= {
        "Verilator",
        "Icarus Verilog",
        "SymbiYosys",
        "pytest",
    }
    assert any(item["path"] == "README.md" for item in data["guidance"])


def test_duplicate_declarations_are_reported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write(repo / "a.sv", "module dup; endmodule\n")
    write(repo / "b.sv", "module dup; endmodule\n")

    repository_map = discover_repository(repo)

    assert repository_map.hierarchy.duplicate_declarations[0].name == "dup"


def test_makefile_command_detection() -> None:
    commands = discover_build_commands(
        "Makefile",
        "lint:\n\tverilator --lint-only top.sv\nsynth:\n\tyosys -p synth\n",
    )

    assert [(command.label, command.tool) for command in commands] == [
        ("lint", "Verilator"),
        ("synth", "Yosys"),
    ]


def test_invalid_repository_fails(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError):
        discover_repository(tmp_path / "missing")


def test_git_metadata_for_temporary_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    write(repo / "top.sv", "module top; endmodule\n")

    repository_map = discover_repository(repo)

    assert repository_map.git.is_git_repository is True
    assert repository_map.git.dirty is True
