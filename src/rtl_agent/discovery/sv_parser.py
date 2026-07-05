from __future__ import annotations

import re
from dataclasses import dataclass, field

from rtl_agent.repository_map import DeclarationKind, SourceDeclaration, SourceFileInfo

DECLARATION_RE = re.compile(
    r"(?m)^\s*(?P<kind>module|interface|package|program|checker)\s+"
    r"(?:automatic\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\b"
)
INCLUDE_RE = re.compile(r'(?m)^\s*`include\s+"(?P<path>[^"]+)"')
IMPORT_RE = re.compile(r"(?m)^\s*import\s+(?P<package>[A-Za-z_][A-Za-z0-9_$]*)::")
INSTANCE_RE = re.compile(
    r"(?m)^\s*(?P<type>[A-Za-z_][A-Za-z0-9_$]*)"
    r"(?:\s*#\s*\((?:[^;]|\n)*?\))?"
    r"\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\s*\(",
    re.MULTILINE,
)
KEYWORDS = {
    "always",
    "always_comb",
    "always_ff",
    "always_latch",
    "assign",
    "assert",
    "assume",
    "begin",
    "case",
    "checker",
    "class",
    "cover",
    "else",
    "end",
    "endchecker",
    "endclass",
    "endfunction",
    "endmodule",
    "endpackage",
    "endprogram",
    "endproperty",
    "endsequence",
    "endtask",
    "for",
    "forever",
    "fork",
    "function",
    "generate",
    "if",
    "import",
    "initial",
    "interface",
    "localparam",
    "logic",
    "module",
    "package",
    "parameter",
    "program",
    "property",
    "sequence",
    "task",
    "typedef",
    "wire",
}


@dataclass
class ParsedSource:
    info: SourceFileInfo = field(default_factory=SourceFileInfo)


def parse_systemverilog(text: str) -> ParsedSource:
    masked = mask_comments_and_strings(text)
    comment_masked = mask_comments(text)
    declarations = [
        SourceDeclaration(
            kind=DeclarationKind(match.group("kind")),
            name=match.group("name"),
            line=_line_for_offset(masked, match.start("kind")),
        )
        for match in DECLARATION_RE.finditer(masked)
    ]
    includes = sorted({match.group("path") for match in INCLUDE_RE.finditer(comment_masked)})
    imports = sorted({match.group("package") for match in IMPORT_RE.finditer(masked)})
    declared_names = {decl.name for decl in declarations}
    instantiations = sorted(
        {
            match.group("type")
            for match in INSTANCE_RE.finditer(masked)
            if _is_plausible_instantiation(match.group("type"), match.group("name"), declared_names)
        }
    )
    return ParsedSource(
        SourceFileInfo(
            declarations=declarations,
            includes=includes,
            imports=imports,
            instantiations=instantiations,
        )
    )


def mask_comments_and_strings(text: str) -> str:
    chars = list(text)
    index = 0
    while index < len(chars):
        pair = "".join(chars[index : index + 2])
        if pair == "//":
            end = text.find("\n", index)
            end = len(chars) if end == -1 else end
            _mask_range(chars, index, end)
            index = end
            continue
        if pair == "/*":
            end = text.find("*/", index + 2)
            end = len(chars) if end == -1 else end + 2
            _mask_range(chars, index, end)
            index = end
            continue
        if chars[index] == '"':
            end = index + 1
            escaped = False
            while end < len(chars):
                if chars[end] == '"' and not escaped:
                    end += 1
                    break
                escaped = chars[end] == "\\" and not escaped
                if chars[end] != "\\":
                    escaped = False
                end += 1
            _mask_range(chars, index, end)
            index = end
            continue
        index += 1
    return "".join(chars)


def mask_comments(text: str) -> str:
    chars = list(text)
    index = 0
    while index < len(chars):
        pair = "".join(chars[index : index + 2])
        if pair == "//":
            end = text.find("\n", index)
            end = len(chars) if end == -1 else end
            _mask_range(chars, index, end)
            index = end
            continue
        if pair == "/*":
            end = text.find("*/", index + 2)
            end = len(chars) if end == -1 else end + 2
            _mask_range(chars, index, end)
            index = end
            continue
        index += 1
    return "".join(chars)


def _mask_range(chars: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if chars[i] != "\n":
            chars[i] = " "


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _is_plausible_instantiation(
    instance_type: str, instance_name: str, declared_names: set[str]
) -> bool:
    lower_type = instance_type.lower()
    lower_name = instance_name.lower()
    if lower_type in KEYWORDS or lower_name in KEYWORDS:
        return False
    if instance_type in declared_names:
        return False
    return lower_type not in {"input", "output", "inout", "ref"}
