from __future__ import annotations

from collections import defaultdict

from rtl_agent.repository_map import (
    DeclarationKind,
    DuplicateDeclaration,
    FileCategory,
    FileRecord,
    HierarchyInfo,
    SourceDeclaration,
    TopCandidate,
)


def infer_hierarchy(files: list[FileRecord], build_references: list[str]) -> HierarchyInfo:
    modules: dict[str, tuple[SourceDeclaration, FileRecord]] = {}
    declarations_by_key: dict[tuple[DeclarationKind, str], list[str]] = defaultdict(list)
    instantiated: set[str] = set()
    testbench_files: set[str] = set()

    for record in files:
        if FileCategory.TESTBENCH in record.categories:
            testbench_files.add(record.path)
        if not record.source:
            continue
        instantiated.update(record.source.instantiations)
        for declaration in record.source.declarations:
            declarations_by_key[(declaration.kind, declaration.name)].append(
                f"{record.path}:{declaration.line}"
            )
            if declaration.kind == DeclarationKind.MODULE:
                modules.setdefault(declaration.name, (declaration, record))

    duplicate_declarations = [
        DuplicateDeclaration(kind=kind, name=name, locations=sorted(locations))
        for (kind, name), locations in declarations_by_key.items()
        if len(locations) > 1
    ]
    declared_module_names = set(modules)
    unresolved = sorted(instantiated - declared_module_names)
    uninstantiated = sorted(declared_module_names - instantiated)
    design_candidates: list[TopCandidate] = []
    tb_candidates: list[TopCandidate] = []
    refs = [ref.lower() for ref in build_references]

    for name, (declaration, record) in modules.items():
        score, reasons = _score_module(name, record, name in uninstantiated, refs)
        candidate = TopCandidate(
            name=name,
            score=score,
            reasons=reasons,
            declaration_path=record.path,
            declaration_line=declaration.line,
            is_testbench=record.path in testbench_files,
        )
        if candidate.is_testbench:
            tb_candidates.append(candidate)
        else:
            design_candidates.append(candidate)

    return HierarchyInfo(
        instantiated_types=sorted(instantiated),
        uninstantiated_modules=uninstantiated,
        unresolved_instantiations=unresolved,
        duplicate_declarations=sorted(
            duplicate_declarations, key=lambda item: (item.kind, item.name)
        ),
        design_top_candidates=sorted(
            design_candidates, key=lambda item: (-item.score, item.name, item.declaration_path)
        ),
        testbench_top_candidates=sorted(
            tb_candidates, key=lambda item: (-item.score, item.name, item.declaration_path)
        ),
    )


def _score_module(
    name: str, record: FileRecord, is_uninstantiated: bool, build_references: list[str]
) -> tuple[int, list[str]]:
    lowered_name = name.lower()
    lowered_path = record.path.lower()
    score = 0
    reasons: list[str] = []
    if is_uninstantiated:
        score += 40
        reasons.append("module is not instantiated by another discovered module")
    if any(token in lowered_name for token in ("top", "soc", "core", "dut")):
        score += 20
        reasons.append("module name matches common top-level naming")
    if any(token in lowered_path for token in ("top", "rtl", "src", "design")):
        score += 10
        reasons.append("file path matches design source patterns")
    if any(record.path.lower() in ref or lowered_name in ref for ref in build_references):
        score += 15
        reasons.append("module or file is referenced by discovered build text")
    if FileCategory.TESTBENCH in record.categories:
        score += 30
        reasons.append("file has testbench indicators")
    if not reasons:
        reasons.append("module declaration discovered")
    return score, reasons
