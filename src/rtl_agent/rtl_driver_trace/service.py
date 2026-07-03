from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from rtl_agent.repository_map import RepositoryMap
from rtl_agent.rtl_driver_trace_models import (
    DependencyEdge,
    DriverStatement,
    EvidenceLabel,
    RtlDriverTraceReport,
    StatementKind,
    TracedSignal,
    TraceNode,
    TraceStatus,
)
from rtl_agent.signal_source_map_models import (
    SignalMappingStatus,
    SignalSourceMapping,
    SignalSourceMapReport,
)

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_MATCHES_PER_FILE = 500
_GUARD_LOOKBACK = 12
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
# Verilog sized/based literals such as 1'b0, 8'hFF, 4'd10 whose base+value tail
# would otherwise be mistaken for an identifier.
_BASED_LITERAL_RE = re.compile(r"\d*'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ_]+")
_ASSIGN_RE = re.compile(r"^\s*assign\s+(?P<lhs>[^=]+?)\s*=\s*(?P<rhs>.+?)\s*;")
_NONBLOCKING_RE = re.compile(
    r"^\s*(?P<lhs>[A-Za-z_][A-Za-z0-9_$]*(?:\s*\[[^\]]*\])?)\s*<=\s*(?P<rhs>.+?)\s*;"
)
_BLOCKING_RE = re.compile(
    r"^\s*(?P<lhs>[A-Za-z_][A-Za-z0-9_$]*(?:\s*\[[^\]]*\])?)\s*=\s*(?P<rhs>[^=].*?)\s*;"
)
_PORT_RE = re.compile(r"\.\s*(?P<port>[A-Za-z_][A-Za-z0-9_$]*)\s*\(\s*(?P<expr>[^()]*)\)")
_GUARD_RE = re.compile(r"(if\s*\(|else\s+if\s*\(|else\b|case\s*\(|always\s*@)")

_KEYWORDS = frozenset(
    {
        "module",
        "endmodule",
        "input",
        "output",
        "inout",
        "logic",
        "wire",
        "reg",
        "bit",
        "int",
        "integer",
        "byte",
        "shortint",
        "longint",
        "real",
        "time",
        "assign",
        "always",
        "always_ff",
        "always_comb",
        "always_latch",
        "initial",
        "begin",
        "end",
        "if",
        "else",
        "case",
        "casex",
        "casez",
        "endcase",
        "posedge",
        "negedge",
        "or",
        "and",
        "not",
        "xor",
        "nand",
        "nor",
        "xnor",
        "for",
        "while",
        "do",
        "repeat",
        "forever",
        "generate",
        "endgenerate",
        "genvar",
        "parameter",
        "localparam",
        "typedef",
        "struct",
        "union",
        "enum",
        "packed",
        "signed",
        "unsigned",
        "import",
        "package",
        "endpackage",
        "interface",
        "endinterface",
        "modport",
        "function",
        "endfunction",
        "task",
        "endtask",
        "return",
        "default",
        "unique",
        "unique0",
        "priority",
        "assert",
        "assume",
        "cover",
        "property",
        "endproperty",
        "sequence",
        "endsequence",
        "const",
        "static",
        "automatic",
        "void",
        "this",
        "super",
        "null",
        "begin_keywords",
        "end_keywords",
    }
)


class RtlDriverTraceError(RuntimeError):
    pass


@dataclass
class _ScannedFile:
    lines: list[str]
    declarations: list[tuple[int, str]]  # (line, name) ascending


def trace_drivers(
    signal_source_map_path: Path,
    repository_map_path: Path,
    *,
    max_depth: int = 2,
    max_nodes: int = 64,
) -> RtlDriverTraceReport:
    if max_depth < 0:
        raise RtlDriverTraceError("max depth must not be negative")
    if max_nodes < 1:
        raise RtlDriverTraceError("max nodes must be at least 1")

    signal_map = _load_signal_map(signal_source_map_path)
    repository_map = _load_repository_map(repository_map_path)
    repository_root = repository_map.repository_root
    declarations_by_file = _declarations_by_file(repository_map)

    warnings: list[str] = []
    cache: dict[str, _ScannedFile | None] = {}

    traced_signals: list[TracedSignal] = []
    relevant_files: set[str] = set()
    seed_leaves: list[str] = []
    for mapping in signal_map.mappings:
        traced = _trace_signal(mapping, repository_root, declarations_by_file, cache, warnings)
        traced_signals.append(traced)
        if traced.status != TraceStatus.UNMAPPED:
            relevant_files.update(traced.searched_files)
            seed_leaves.append(mapping.leaf)

    nodes, edges, unresolved, truncated = _expand_dependencies(
        sorted(dict.fromkeys(seed_leaves)),
        sorted(relevant_files),
        repository_root,
        declarations_by_file,
        cache,
        max_depth,
        max_nodes,
    )
    if truncated:
        warnings.append(
            f"dependency expansion truncated at max_depth={max_depth}/max_nodes={max_nodes}"
        )

    return RtlDriverTraceReport(
        signal_source_map_path=signal_source_map_path.resolve(),
        repository_map_path=repository_map_path.resolve(),
        repository_root=repository_root,
        max_depth=max_depth,
        max_nodes=max_nodes,
        traced_signals=sorted(traced_signals, key=lambda item: item.signal),
        dependency_nodes=nodes,
        dependency_edges=edges,
        unresolved_identifiers=unresolved,
        truncated=truncated,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "Driver and dependency evidence is a bounded, deterministic textual scan of RTL "
            "source; it is never elaborated, simulated, or semantically resolved.",
            "Edges are labeled 'textual' (identifier appears in a matched assignment) or "
            "'inferred_textual' (name-based port connection); ambiguity and unresolved "
            "identifiers are preserved, and multiple drivers are never collapsed to one.",
        ],
    )


def write_driver_trace(report: RtlDriverTraceReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise RtlDriverTraceError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_signal_map(path: Path) -> SignalSourceMapReport:
    try:
        return SignalSourceMapReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise RtlDriverTraceError(f"could not load signal-source map: {path}") from exc


def _load_repository_map(path: Path) -> RepositoryMap:
    try:
        return RepositoryMap.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise RtlDriverTraceError(f"could not load repository map: {path}") from exc


def _declarations_by_file(repository_map: RepositoryMap) -> dict[str, list[tuple[int, str]]]:
    result: dict[str, list[tuple[int, str]]] = {}
    for file_record in repository_map.files:
        if file_record.source is None:
            continue
        entries = sorted(
            (declaration.line, declaration.name) for declaration in file_record.source.declarations
        )
        if entries:
            result[file_record.path] = entries
    return result


def _trace_signal(
    mapping: SignalSourceMapping,
    repository_root: Path,
    declarations_by_file: dict[str, list[tuple[int, str]]],
    cache: dict[str, _ScannedFile | None],
    warnings: list[str],
) -> TracedSignal:
    signal = mapping.signal
    leaf = mapping.leaf
    status = mapping.status
    candidates = mapping.candidates

    if status == SignalMappingStatus.UNRESOLVED or not candidates:
        warnings.append(f"signal is unmapped; cannot trace drivers: {signal}")
        return TracedSignal(
            signal=signal,
            leaf=leaf,
            status=TraceStatus.UNMAPPED,
            mapping_status=str(status),
            searched_files=[],
            drivers=[],
        )

    searched = sorted({candidate.file_path for candidate in candidates})
    drivers: list[DriverStatement] = []
    for file_path in searched:
        scanned = _get_file(file_path, repository_root, declarations_by_file, cache)
        if scanned is None:
            warnings.append(f"declaring file could not be read: {file_path}")
            continue
        drivers.extend(_scan_for_identifier(file_path, scanned, leaf))
    drivers.sort(key=lambda item: (item.file_path, item.line, str(item.kind)))
    trace_status = TraceStatus.TRACED if drivers else TraceStatus.NO_DRIVERS
    return TracedSignal(
        signal=signal,
        leaf=leaf,
        status=trace_status,
        mapping_status=str(status),
        searched_files=searched,
        drivers=drivers,
    )


def _get_file(
    file_path: str,
    repository_root: Path,
    declarations_by_file: dict[str, list[tuple[int, str]]],
    cache: dict[str, _ScannedFile | None],
) -> _ScannedFile | None:
    if file_path in cache:
        return cache[file_path]
    absolute = (repository_root / file_path).resolve()
    scanned: _ScannedFile | None = None
    if absolute.exists() and absolute.is_file() and absolute.stat().st_size <= MAX_FILE_BYTES:
        masked = _mask(absolute.read_text(encoding="utf-8", errors="replace"))
        scanned = _ScannedFile(
            lines=masked.splitlines(),
            declarations=declarations_by_file.get(file_path, []),
        )
    cache[file_path] = scanned
    return scanned


def _scan_for_identifier(
    file_path: str, scanned: _ScannedFile, identifier: str
) -> list[DriverStatement]:
    word = re.compile(rf"(?<![A-Za-z0-9_$]){re.escape(identifier)}(?![A-Za-z0-9_$])")
    statements: list[DriverStatement] = []
    for index, line in enumerate(scanned.lines):
        if len(statements) >= MAX_MATCHES_PER_FILE:
            break
        if not word.search(line):
            continue
        statement = _classify_line(file_path, scanned, index, line, identifier, word)
        if statement is not None:
            statements.append(statement)
    return statements


def _classify_line(
    file_path: str,
    scanned: _ScannedFile,
    index: int,
    line: str,
    identifier: str,
    word: re.Pattern[str],
) -> DriverStatement | None:
    number = index + 1
    text = line.strip()[:400]
    enclosing = _enclosing_declaration(scanned.declarations, number)

    assign = _ASSIGN_RE.match(line)
    if assign and word.search(assign.group("lhs")):
        return DriverStatement(
            file_path=file_path,
            line=number,
            kind=StatementKind.CONTINUOUS_ASSIGN,
            label=EvidenceLabel.TEXTUAL,
            statement_text=text,
            lhs_identifiers=_identifiers(assign.group("lhs")),
            rhs_identifiers=_identifiers(assign.group("rhs")),
            enclosing_declaration=enclosing,
        )

    if not assign:
        procedural = _NONBLOCKING_RE.match(line) or _BLOCKING_RE.match(line)
        if procedural and word.search(procedural.group("lhs")):
            lhs_ids = _identifiers(procedural.group("lhs"))
            if lhs_ids and lhs_ids[0] not in _KEYWORDS:
                return DriverStatement(
                    file_path=file_path,
                    line=number,
                    kind=StatementKind.PROCEDURAL_ASSIGN,
                    label=EvidenceLabel.TEXTUAL,
                    statement_text=text,
                    lhs_identifiers=lhs_ids,
                    rhs_identifiers=_identifiers(procedural.group("rhs")),
                    enclosing_declaration=enclosing,
                    guard=_guard(scanned.lines, index),
                )

    for port in _PORT_RE.finditer(line):
        if word.search(port.group("expr")):
            return DriverStatement(
                file_path=file_path,
                line=number,
                kind=StatementKind.PORT_CONNECTION,
                label=EvidenceLabel.INFERRED_TEXTUAL,
                statement_text=text,
                lhs_identifiers=[port.group("port")],
                rhs_identifiers=_identifiers(port.group("expr")),
                enclosing_declaration=enclosing,
            )

    # A bare textual occurrence (declaration, RHS usage elsewhere, etc.) is not a
    # driver or port connection, so it is not recorded as candidate evidence.
    return None


def _expand_dependencies(
    seeds: list[str],
    relevant_files: list[str],
    repository_root: Path,
    declarations_by_file: dict[str, list[tuple[int, str]]],
    cache: dict[str, _ScannedFile | None],
    max_depth: int,
    max_nodes: int,
) -> tuple[list[TraceNode], list[DependencyEdge], list[str], bool]:
    visited: dict[str, int] = {}
    nodes: list[TraceNode] = []
    edges: list[DependencyEdge] = []
    unresolved: set[str] = set()
    truncated = False
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)

    while queue:
        identifier, depth = queue.popleft()
        if identifier in visited:
            continue
        if len(visited) >= max_nodes:
            truncated = True
            break
        visited[identifier] = depth

        drivers = _drivers_for(
            identifier, relevant_files, repository_root, declarations_by_file, cache
        )
        assign_drivers = [
            driver
            for driver in drivers
            if driver.kind in (StatementKind.CONTINUOUS_ASSIGN, StatementKind.PROCEDURAL_ASSIGN)
        ]
        nodes.append(
            TraceNode(
                identifier=identifier,
                depth=depth,
                resolved=bool(assign_drivers),
                driver_count=len(assign_drivers),
            )
        )
        if not assign_drivers:
            unresolved.add(identifier)
        if depth >= max_depth:
            continue
        for driver in drivers:
            for dependency in driver.rhs_identifiers:
                if dependency == identifier:
                    continue
                edges.append(
                    DependencyEdge(
                        source_signal=identifier,
                        depends_on=dependency,
                        label=driver.label,
                        statement_kind=driver.kind,
                        evidence_file=driver.file_path,
                        evidence_line=driver.line,
                    )
                )
                queue.append((dependency, depth + 1))

    nodes.sort(key=lambda item: (item.depth, item.identifier))
    edges.sort(
        key=lambda item: (
            item.source_signal,
            item.depends_on,
            item.evidence_file,
            item.evidence_line,
        )
    )
    return nodes, _dedupe_edges(edges), sorted(unresolved), truncated


def _drivers_for(
    identifier: str,
    relevant_files: list[str],
    repository_root: Path,
    declarations_by_file: dict[str, list[tuple[int, str]]],
    cache: dict[str, _ScannedFile | None],
) -> list[DriverStatement]:
    drivers: list[DriverStatement] = []
    for file_path in relevant_files:
        scanned = _get_file(file_path, repository_root, declarations_by_file, cache)
        if scanned is None:
            continue
        for statement in _scan_for_identifier(file_path, scanned, identifier):
            if statement.kind == StatementKind.OTHER_REFERENCE:
                continue
            if (
                statement.kind == StatementKind.PORT_CONNECTION
                or identifier in statement.lhs_identifiers
            ):
                drivers.append(statement)
    return drivers


def _dedupe_edges(edges: list[DependencyEdge]) -> list[DependencyEdge]:
    seen: set[tuple[str, str, str, str, int]] = set()
    result: list[DependencyEdge] = []
    for edge in edges:
        key = (
            edge.source_signal,
            edge.depends_on,
            str(edge.statement_kind),
            edge.evidence_file,
            edge.evidence_line,
        )
        if key not in seen:
            seen.add(key)
            result.append(edge)
    return result


def _enclosing_declaration(declarations: list[tuple[int, str]], line: int) -> str | None:
    enclosing: str | None = None
    for declaration_line, name in declarations:
        if declaration_line <= line:
            enclosing = name
        else:
            break
    return enclosing


def _guard(lines: list[str], index: int) -> str | None:
    for offset in range(1, _GUARD_LOOKBACK + 1):
        position = index - offset
        if position < 0:
            break
        candidate = lines[position].strip()
        if _GUARD_RE.search(candidate):
            return candidate[:200]
    return None


def _identifiers(expression: str) -> list[str]:
    cleaned = _BASED_LITERAL_RE.sub(" ", expression)
    result: list[str] = []
    for token in _IDENTIFIER_RE.findall(cleaned):
        if token not in _KEYWORDS and token not in result:
            result.append(token)
    return result


def _mask(text: str) -> str:
    text = re.sub(
        r"/\*.*?\*/", lambda match: re.sub(r"[^\n]", " ", match.group()), text, flags=re.S
    )
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r'"(\\.|[^"\\])*"', '""', text)
    return text
