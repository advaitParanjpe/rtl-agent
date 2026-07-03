from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from rtl_agent.waveform_slice_models import (
    WaveformInitialValue,
    WaveformParseStatistics,
    WaveformSignal,
    WaveformSliceReport,
    WaveformSourceMetadata,
    WaveformValueChange,
    WaveformValueKind,
    WaveformWindow,
)

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_SELECTED_SIGNALS = 4096
MAX_WINDOW_VALUE_CHANGES = 20_000
_RANGE_RE = re.compile(r"^\[\d+(?::\d+)?\]$")
_DUMP_DIRECTIVES = frozenset({"$dumpvars", "$dumpall", "$dumpon", "$dumpoff"})


class WaveformSliceError(RuntimeError):
    pass


@dataclass
class _Variable:
    identifier: str
    name: str
    var_type: str
    width: int
    kind: WaveformValueKind
    bit_range: str | None


def extract_waveform_window(
    vcd_path: Path,
    failure_time: int,
    before: int,
    after: int,
    signal_names: list[str] | None = None,
    signal_prefixes: list[str] | None = None,
) -> WaveformSliceReport:
    if failure_time < 0:
        raise WaveformSliceError("failure time must not be negative")
    if before < 0 or after < 0:
        raise WaveformSliceError("window before/after must not be negative")

    resolved = vcd_path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise WaveformSliceError(f"VCD file does not exist: {vcd_path}")
    size_bytes = resolved.stat().st_size
    if size_bytes > MAX_FILE_BYTES:
        raise WaveformSliceError(
            f"VCD file exceeds the bounded size limit of {MAX_FILE_BYTES} bytes"
        )

    warnings: list[str] = []
    requested_start = failure_time - before
    if requested_start < 0:
        warnings.append("requested window start clamped to 0")
        requested_start = 0
    requested_end = failure_time + after

    variables, timescale, scopes = _parse_header(resolved)

    selected, selection_warnings = _select_variables(
        variables, signal_names or [], signal_prefixes or []
    )
    warnings.extend(selection_warnings)
    selected_ids = {variable.identifier for variable in selected}

    scan = _scan_value_changes(resolved, selected_ids, requested_start, requested_end)
    warnings.extend(scan.warnings)

    if timescale is None:
        warnings.append("timescale not found in VCD header")
    if not scan.saw_timestamp:
        warnings.append("no timestamps found in the value-change section")
    if not scan.window_changes:
        warnings.append("no value changes found within the requested window")

    value_changes = _expand_value_changes(scan.window_changes, selected)
    initial_values = _initial_values(selected, scan.pre_window_value)
    observed_start = min((change.time for change in value_changes), default=None)
    observed_end = max((change.time for change in value_changes), default=None)

    return WaveformSliceReport(
        source=WaveformSourceMetadata(
            path=resolved,
            size_bytes=size_bytes,
            sha256=_sha256(resolved),
            timescale=timescale,
        ),
        window=WaveformWindow(
            failure_time=failure_time,
            before=before,
            after=after,
            requested_start=requested_start,
            requested_end=requested_end,
            observed_start=observed_start,
            observed_end=observed_end,
        ),
        selected_signals=[
            WaveformSignal(
                name=variable.name,
                identifier=variable.identifier,
                var_type=variable.var_type,
                width=variable.width,
                kind=variable.kind,
                bit_range=variable.bit_range,
            )
            for variable in selected
        ],
        initial_values=initial_values,
        value_changes=value_changes,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=[
            "Waveform slice is deterministic and bounded to the requested time window; "
            "the full waveform is not copied.",
            "Values are recorded verbatim from the VCD (scalar 0/1/x/z, vector bit strings, "
            "real numbers); no causal or root-cause meaning is inferred.",
        ],
        parse_statistics=WaveformParseStatistics(
            scopes=scopes,
            declared_variables=len(variables),
            selected_signals=len(selected),
            timestamps_total=scan.timestamps_total,
            value_changes_total=scan.value_changes_total,
            value_changes_in_window=len(value_changes),
            truncated=scan.truncated,
        ),
    )


def write_waveform_slice(report: WaveformSliceReport, output: Path) -> None:
    _ensure_safe_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ensure_safe_output(output: Path) -> None:
    if str(output) == "":
        raise WaveformSliceError("output path must not be empty")
    if output.exists() and output.is_dir():
        raise WaveformSliceError(f"output path is a directory: {output}")


def read_vcd_timescale(vcd_path: Path) -> str | None:
    """Return the VCD timescale string, reusing the shared header parser.

    Raises ``WaveformSliceError`` when the file is missing or the header is
    malformed, matching ``extract_waveform_window``.
    """

    resolved = vcd_path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise WaveformSliceError(f"VCD file does not exist: {vcd_path}")
    _, timescale, _ = _parse_header(resolved)
    return timescale


def _parse_header(path: Path) -> tuple[list[_Variable], str | None, int]:
    tokens = _iter_tokens(path)
    timescale: str | None = None
    scope_stack: list[str] = []
    variables: list[_Variable] = []
    scopes = 0
    saw_enddefinitions = False

    for token in tokens:
        if token == "$enddefinitions":
            _collect_until_end(tokens, token)
            saw_enddefinitions = True
            break
        if token == "$timescale":
            parts = _collect_until_end(tokens, token)
            timescale = " ".join(parts) or None
        elif token == "$scope":
            parts = _collect_until_end(tokens, token)
            scope_stack.append(parts[-1] if parts else "")
            scopes += 1
        elif token == "$upscope":
            _collect_until_end(tokens, token)
            if scope_stack:
                scope_stack.pop()
        elif token == "$var":
            parts = _collect_until_end(tokens, token)
            variables.append(_parse_var(parts, scope_stack))
        elif token in {"$date", "$version", "$comment"}:
            _collect_until_end(tokens, token)
        # Any other stray header token is ignored deterministically.

    if not saw_enddefinitions:
        raise WaveformSliceError("malformed VCD: missing $enddefinitions before end of file")
    return variables, timescale, scopes


def _parse_var(parts: list[str], scope_stack: list[str]) -> _Variable:
    if len(parts) < 4:
        raise WaveformSliceError(f"malformed VCD $var declaration: {' '.join(parts)}")
    var_type = parts[0]
    try:
        width = int(parts[1])
    except ValueError as exc:
        raise WaveformSliceError(f"malformed VCD $var width: {' '.join(parts)}") from exc
    if width < 1:
        raise WaveformSliceError(f"malformed VCD $var width: {' '.join(parts)}")
    identifier = parts[2]
    reference = parts[3]
    extra = parts[4:]
    bit_range = extra[0] if extra and _RANGE_RE.match(extra[0]) else None
    name = ".".join([*scope_stack, reference])
    if var_type == "real":
        kind = WaveformValueKind.REAL
    elif width > 1:
        kind = WaveformValueKind.VECTOR
    else:
        kind = WaveformValueKind.SCALAR
    return _Variable(
        identifier=identifier,
        name=name,
        var_type=var_type,
        width=width,
        kind=kind,
        bit_range=bit_range,
    )


@dataclass
class _ScanResult:
    pre_window_value: dict[str, str]
    window_changes: list[tuple[int, str, str]]
    timestamps_total: int
    value_changes_total: int
    saw_timestamp: bool
    truncated: bool
    warnings: list[str]


def _scan_value_changes(
    path: Path, selected_ids: set[str], requested_start: int, requested_end: int
) -> _ScanResult:
    tokens = _skip_to_definitions_body(path)
    pre_window_value: dict[str, str] = {}
    window_changes: list[tuple[int, str, str]] = []
    timestamps_total = 0
    value_changes_total = 0
    saw_timestamp = False
    truncated = False
    current_time = 0

    for token in tokens:
        first = token[0]
        if first == "#":
            try:
                current_time = int(token[1:])
            except ValueError as exc:
                raise WaveformSliceError(f"malformed VCD timestamp: {token}") from exc
            saw_timestamp = True
            timestamps_total += 1
            continue
        if token == "$comment":
            _collect_until_end(tokens, token)
            continue
        if token == "$end" or token in _DUMP_DIRECTIVES:
            continue
        if first in {"b", "B", "r", "R"}:
            value = token[1:]
            identifier = next(tokens, None)
            if identifier is None:
                raise WaveformSliceError("malformed VCD: value change missing identifier")
            normalized = value if first in {"r", "R"} else value.lower()
        else:
            if len(token) < 2:
                continue
            normalized = first.lower()
            identifier = token[1:]
        value_changes_total += 1
        if identifier not in selected_ids:
            continue
        if current_time < requested_start:
            pre_window_value[identifier] = normalized
        elif current_time <= requested_end:
            if len(window_changes) < MAX_WINDOW_VALUE_CHANGES:
                window_changes.append((current_time, identifier, normalized))
            else:
                truncated = True

    warnings: list[str] = []
    if truncated:
        warnings.append(
            f"value changes truncated to the bounded limit of {MAX_WINDOW_VALUE_CHANGES}"
        )
    return _ScanResult(
        pre_window_value=pre_window_value,
        window_changes=window_changes,
        timestamps_total=timestamps_total,
        value_changes_total=value_changes_total,
        saw_timestamp=saw_timestamp,
        truncated=truncated,
        warnings=warnings,
    )


def _select_variables(
    variables: list[_Variable], names: list[str], prefixes: list[str]
) -> tuple[list[_Variable], list[str]]:
    warnings: list[str] = []
    if not names and not prefixes:
        selected = list(variables)
    else:
        name_set = set(names)
        selected = []
        for variable in variables:
            if variable.name in name_set or any(
                variable.name == prefix or variable.name.startswith(prefix + ".")
                for prefix in prefixes
            ):
                selected.append(variable)
        known = {variable.name for variable in variables}
        for missing in sorted(set(names) - known):
            warnings.append(f"requested signal not found: {missing}")
        if not selected:
            warnings.append("no signals matched the requested selection")
    selected = sorted(selected, key=lambda variable: (variable.name, variable.identifier))
    if len(selected) > MAX_SELECTED_SIGNALS:
        warnings.append(
            f"selected signals truncated to the bounded limit of {MAX_SELECTED_SIGNALS}"
        )
        selected = selected[:MAX_SELECTED_SIGNALS]
    return selected, warnings


def _expand_value_changes(
    window_changes: list[tuple[int, str, str]], selected: list[_Variable]
) -> list[WaveformValueChange]:
    by_identifier: dict[str, list[_Variable]] = {}
    for variable in selected:
        by_identifier.setdefault(variable.identifier, []).append(variable)
    changes: list[WaveformValueChange] = []
    for time, identifier, value in window_changes:
        for variable in by_identifier.get(identifier, []):
            changes.append(
                WaveformValueChange(
                    time=time, signal=variable.name, identifier=identifier, value=value
                )
            )
    return sorted(changes, key=lambda change: (change.time, change.signal, change.identifier))


def _initial_values(
    selected: list[_Variable], pre_window_value: dict[str, str]
) -> list[WaveformInitialValue]:
    initial: list[WaveformInitialValue] = []
    for variable in selected:
        if variable.identifier in pre_window_value:
            initial.append(
                WaveformInitialValue(
                    signal=variable.name,
                    identifier=variable.identifier,
                    determinable=True,
                    value=pre_window_value[variable.identifier],
                )
            )
        else:
            initial.append(
                WaveformInitialValue(
                    signal=variable.name,
                    identifier=variable.identifier,
                    determinable=False,
                    value=None,
                )
            )
    return sorted(initial, key=lambda item: (item.signal, item.identifier))


def _iter_tokens(path: Path) -> Iterator[str]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            yield from line.split()


def _skip_to_definitions_body(path: Path) -> Iterator[str]:
    tokens = _iter_tokens(path)
    for token in tokens:
        if token == "$enddefinitions":
            _collect_until_end(tokens, token)
            break
    return tokens


def _collect_until_end(tokens: Iterator[str], keyword: str) -> list[str]:
    collected: list[str] = []
    for token in tokens:
        if token == "$end":
            return collected
        collected.append(token)
    raise WaveformSliceError(f"malformed VCD: unterminated {keyword} section (missing $end)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
