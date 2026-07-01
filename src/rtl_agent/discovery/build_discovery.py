from __future__ import annotations

from pathlib import Path

from rtl_agent.repository_map import DiscoveredCommand, FlowCategory

TOOL_KEYWORDS = {
    "verilator": "Verilator",
    "iverilog": "Icarus Verilog",
    "vvp": "Icarus Verilog",
    "yosys": "Yosys",
    "sby": "SymbiYosys",
    "cocotb": "cocotb",
    "pytest": "pytest",
    "make": "Make",
    "vcs": "VCS",
    "xrun": "Xcelium",
    "questa": "Questa",
    "vsim": "Questa",
}
CATEGORY_KEYWORDS = {
    FlowCategory.LINT: ("lint", "verilator --lint", "verible"),
    FlowCategory.COMPILE: ("compile", "build", "iverilog", "verilator"),
    FlowCategory.SIMULATION: ("sim", "simulate", "vvp", "vsim", "xrun", "vcs"),
    FlowCategory.UNIT_TEST: ("test", "pytest", "cocotb"),
    FlowCategory.REGRESSION: ("regress", "regression"),
    FlowCategory.FORMAL: ("formal", "sby", "symbiyosys"),
    FlowCategory.SYNTHESIS: ("synth", "yosys"),
    FlowCategory.COVERAGE: ("coverage", "cov"),
    FlowCategory.FORMATTING: ("format", "fmt", "verible-verilog-format"),
}


def discover_build_commands(path: str, text: str) -> list[DiscoveredCommand]:
    file_name = Path(path).name
    if file_name == "Makefile" or path.endswith(".mk"):
        return _discover_makefile(path, text)
    return _discover_text_commands(path, text)


def _discover_makefile(path: str, text: str) -> list[DiscoveredCommand]:
    commands: list[DiscoveredCommand] = []
    current_target: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(("\t", " ")) and ":" in line:
            target = line.split(":", 1)[0].strip()
            if target and not any(char in target for char in " =$"):
                current_target = (target, number)
            continue
        if current_target and line.startswith(("\t", " ")):
            command_text = stripped.lstrip("@-")
            if command_text:
                commands.append(
                    _command(path, current_target[0], command_text, number, "make target command")
                )
    return sorted(commands, key=lambda item: (item.source_file, item.line, item.label))


def _discover_text_commands(path: str, text: str) -> list[DiscoveredCommand]:
    commands: list[DiscoveredCommand] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        lowered = stripped.lower()
        if any(tool in lowered for tool in TOOL_KEYWORDS):
            label = Path(path).name
            commands.append(_command(path, label, stripped, number, "tool reference"))
    return sorted(commands, key=lambda item: (item.source_file, item.line, item.command_text))


def _command(
    path: str,
    label: str,
    command_text: str,
    line: int,
    evidence_reason: str,
) -> DiscoveredCommand:
    return DiscoveredCommand(
        source_file=path,
        label=label,
        command_text=command_text,
        category=_infer_category(label, command_text),
        tool=_infer_tool(command_text),
        confidence=0.85 if evidence_reason == "make target command" else 0.65,
        evidence=evidence_reason,
        line=line,
    )


def _infer_tool(command_text: str) -> str:
    lowered = command_text.lower()
    for keyword, tool in TOOL_KEYWORDS.items():
        if keyword in lowered:
            return tool
    return "unknown"


def _infer_category(label: str, command_text: str) -> FlowCategory:
    haystack = f"{label} {command_text}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return FlowCategory.UNKNOWN
