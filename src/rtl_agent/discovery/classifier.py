from __future__ import annotations

from pathlib import Path

from rtl_agent.repository_map import FileCategory

SOURCE_EXTENSIONS = {".v", ".sv"}
INCLUDE_EXTENSIONS = {".vh", ".svh"}
BUILD_EXTENSIONS = {".mk", ".tcl", ".ys", ".sby", ".f", ".list", ".yaml", ".yml", ".toml", ".json"}
SCRIPT_EXTENSIONS = {".py"}
DOC_PREFIXES = ("readme", "contributing", "agents")
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CONSTRAINT_EXTENSIONS = {".xdc", ".sdc", ".pcf", ".qsf"}
GENERATED_VENDOR_PARTS = {"vendor", "third_party", "3rdparty", "generated", "gen", "ip"}


def is_relevant_path(path: Path) -> bool:
    name = path.name
    lower = name.lower()
    suffix = path.suffix.lower()
    if suffix in SOURCE_EXTENSIONS | INCLUDE_EXTENSIONS | BUILD_EXTENSIONS | SCRIPT_EXTENSIONS:
        return True
    if suffix in DOC_EXTENSIONS and (
        lower.startswith(DOC_PREFIXES) or "spec" in lower or "design" in lower
    ):
        return True
    if suffix in CONSTRAINT_EXTENSIONS:
        return True
    return name == "Makefile" or name == "CMakeLists.txt"


def classify_file(path: Path, text_sample: str | None = None) -> list[FileCategory]:
    categories: set[FileCategory] = set()
    lower_parts = {part.lower() for part in path.parts}
    lower_name = path.name.lower()
    suffix = path.suffix.lower()

    if lower_parts & GENERATED_VENDOR_PARTS:
        categories.add(FileCategory.GENERATED_VENDOR)
    if suffix in SOURCE_EXTENSIONS:
        categories.add(FileCategory.RTL_SOURCE)
    if suffix in INCLUDE_EXTENSIONS:
        categories.add(FileCategory.INCLUDE)
    if suffix in CONSTRAINT_EXTENSIONS:
        categories.add(FileCategory.CONSTRAINTS)
    if suffix in BUILD_EXTENSIONS or path.name in {"Makefile", "CMakeLists.txt"}:
        categories.add(FileCategory.BUILD_CONFIG)
    if suffix in SCRIPT_EXTENSIONS:
        categories.add(FileCategory.SCRIPT)
    if suffix in DOC_EXTENSIONS or lower_name.startswith(DOC_PREFIXES):
        categories.add(FileCategory.DOCUMENTATION)
    if _looks_like_testbench(path, text_sample):
        categories.add(FileCategory.TESTBENCH)
    if _looks_like_assertion(path, text_sample):
        categories.add(FileCategory.ASSERTION)
    if text_sample:
        if "package " in text_sample:
            categories.add(FileCategory.PACKAGE)
        if "interface " in text_sample:
            categories.add(FileCategory.INTERFACE)

    if not categories and is_relevant_path(path):
        categories.add(FileCategory.UNKNOWN_RELEVANT)
    return sorted(categories, key=str)


def _looks_like_testbench(path: Path, text_sample: str | None) -> bool:
    lowered = "/".join(path.parts).lower()
    if any(token in lowered for token in ("tb", "testbench", "sim", "verification", "verify")):
        return True
    if text_sample is None:
        return False
    sample = text_sample.lower()
    return "initial begin" in sample or "$finish" in sample or "$dumpfile" in sample


def _looks_like_assertion(path: Path, text_sample: str | None) -> bool:
    lowered = "/".join(path.parts).lower()
    if any(token in lowered for token in ("assert", "sva", "property", "checker")):
        return True
    if text_sample is None:
        return False
    sample = text_sample.lower()
    return "assert property" in sample or "cover property" in sample or " checker " in sample
