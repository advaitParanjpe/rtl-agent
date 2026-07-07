from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class InterventionError(RuntimeError):
    """A manual intervention could not be normalized or applied cleanly."""


@dataclass
class PatchIntervention:
    patch_path: Path
    description: str | None = None


@dataclass
class ReplaceIntervention:
    file: str
    old: str
    new: str
    description: str | None = None


Intervention = PatchIntervention | ReplaceIntervention


def normalize_intervention(
    *,
    patch: Path | None,
    replace_file: str | None,
    replace_old: str | None,
    replace_new: str | None,
    description: str | None = None,
) -> Intervention:
    has_patch = patch is not None
    has_replace = replace_file is not None or replace_old is not None or replace_new is not None
    if has_patch and has_replace:
        raise InterventionError("provide either a patch or a replace_text edit, not both")
    if has_patch:
        assert patch is not None
        if not patch.exists() or not patch.is_file():
            raise InterventionError(f"patch file not found: {patch}")
        return PatchIntervention(patch_path=patch.resolve(), description=description)
    if replace_file is None or replace_old is None or replace_new is None:
        raise InterventionError("a replace_text edit requires a file, old text, and new text")
    return ReplaceIntervention(
        file=replace_file, old=replace_old, new=replace_new, description=description
    )


def apply_intervention(
    intervention: Intervention, worktree_path: Path, allowed_files: list[str]
) -> list[str]:
    """Apply a manual intervention inside a worktree; return the files it changed."""

    if isinstance(intervention, PatchIntervention):
        return _apply_patch(intervention.patch_path, worktree_path, allowed_files)
    return _apply_replace(intervention, worktree_path, allowed_files)


def intervention_digest(intervention: Intervention, allowed_files: list[str]) -> str:
    """Deterministic semantic digest over the canonical intervention content."""

    if isinstance(intervention, PatchIntervention):
        payload: dict[str, object] = {
            "kind": "patch",
            "patch": intervention.patch_path.read_text(encoding="utf-8"),
        }
    else:
        payload = {
            "kind": "replace_text",
            "file": intervention.file,
            "old": intervention.old,
            "new": intervention.new,
        }
    payload["allowed_files"] = sorted(allowed_files)
    return sha256((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")).hexdigest()


def _apply_patch(patch_path: Path, worktree_path: Path, allowed_files: list[str]) -> list[str]:
    targets = _patch_target_files(patch_path, worktree_path)
    if not targets:
        raise InterventionError("patch does not modify any files")
    disallowed = [name for name in targets if name not in allowed_files]
    if disallowed:
        raise InterventionError(
            f"intervention targets files not in allowed files: {', '.join(sorted(disallowed))}"
        )
    check = subprocess.run(
        ["git", "-C", str(worktree_path), "apply", "--check", str(patch_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise InterventionError(
            f"patch does not apply cleanly: {check.stderr.strip() or 'git apply --check failed'}"
        )
    applied = subprocess.run(
        ["git", "-C", str(worktree_path), "apply", str(patch_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if applied.returncode != 0:
        raise InterventionError(
            f"patch failed to apply: {applied.stderr.strip() or 'git apply failed'}"
        )
    return sorted(targets)


def _patch_target_files(patch_path: Path, worktree_path: Path) -> list[str]:
    numstat = subprocess.run(
        ["git", "-C", str(worktree_path), "apply", "--numstat", str(patch_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if numstat.returncode != 0:
        raise InterventionError(
            f"patch could not be parsed: {numstat.stderr.strip() or 'git apply --numstat failed'}"
        )
    files: list[str] = []
    for line in numstat.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2]:
            files.append(parts[2])
    return files


def _apply_replace(
    intervention: ReplaceIntervention, worktree_path: Path, allowed_files: list[str]
) -> list[str]:
    if intervention.file not in allowed_files:
        raise InterventionError(
            f"intervention targets a file not in allowed files: {intervention.file}"
        )
    target = (worktree_path / intervention.file).resolve()
    if not target.is_relative_to(worktree_path.resolve()):
        raise InterventionError(f"intervention file escapes the worktree: {intervention.file}")
    if not target.exists() or not target.is_file():
        raise InterventionError(f"intervention file does not exist: {intervention.file}")
    text = target.read_text(encoding="utf-8")
    occurrences = text.count(intervention.old)
    if occurrences != 1:
        raise InterventionError(
            f"replace_text expected exactly one match in {intervention.file}, found {occurrences}"
        )
    target.write_text(text.replace(intervention.old, intervention.new, 1), encoding="utf-8")
    return [intervention.file]
