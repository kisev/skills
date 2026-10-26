"""The safety model: preview, confirmation, ownership, collision, drift.

Every write path goes through one plan type. A plan is built from a desired
state and the recorded ownership; execution refuses to run unconfirmed, with
unresolved collisions, or with drifted files pending a drift decision. Files
skillmate does not own are never touched, and a file the user modified after
installation is never silently overwritten.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MANIFEST_SCHEMA = "skillmate-ownership/v1"
MANIFEST_RELATIVE = ".skillmate/manifest.json"


class SafetyError(Exception):
    """A plan cannot be executed as asked."""


@dataclass(frozen=True)
class OwnedFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class Ownership:
    """The recorded ownership of one host installation."""

    distribution_version: str
    source: str  # "distribution" | "checkout"
    files: tuple[OwnedFile, ...]

    def by_path(self) -> dict[str, str]:
        return {owned.path: owned.sha256 for owned in self.files}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_ownership(root: Path) -> Ownership | None:
    """Read the ownership manifest of a host directory, if any."""
    manifest = root / MANIFEST_RELATIVE
    if not manifest.is_file():
        return None
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SafetyError(f"ownership manifest at {manifest} is unreadable: {error}") from error
    if document.get("schema") != MANIFEST_SCHEMA:
        raise SafetyError(f"ownership manifest at {manifest} has an unknown schema")
    version = document.get("version")
    source = document.get("source")
    files = document.get("files")
    if not isinstance(version, str) or not isinstance(source, str) or not isinstance(files, list):
        raise SafetyError(f"ownership manifest at {manifest} is malformed")
    owned: list[OwnedFile] = []
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise SafetyError(f"ownership manifest at {manifest} has a malformed file entry")
        sha256 = entry.get("sha256")
        if not isinstance(sha256, str):
            raise SafetyError(f"ownership manifest at {manifest} has a file entry without a digest")
        owned.append(OwnedFile(path=entry["path"], sha256=sha256))
    return Ownership(distribution_version=version, source=source, files=tuple(owned))


@dataclass(frozen=True)
class WriteStep:
    path: str
    content: bytes

    def describe(self) -> str:
        return f"write {self.path} ({len(self.content)} bytes)"


@dataclass(frozen=True)
class Plan:
    """A previewable, confirmable set of changes to one host directory."""

    root: Path
    steps: tuple[WriteStep, ...]
    removals: tuple[str, ...]
    collisions: tuple[str, ...]
    drifted: tuple[str, ...]
    missing: tuple[str, ...]
    notices: tuple[str, ...]
    ownership_after: Ownership | None

    @property
    def empty(self) -> bool:
        return not self.steps and not self.removals

    def machine(self) -> dict[str, object]:
        return {
            "schema": "skillmate-plan/v1",
            "root": str(self.root),
            "steps": [step.describe() for step in self.steps],
            "removals": list(self.removals),
            "collisions": list(self.collisions),
            "drifted": list(self.drifted),
            "missing": list(self.missing),
            "notices": list(self.notices),
        }

    def preview(self) -> str:
        lines = [f"plan for {self.root}"]
        lines.extend(f"  {step.describe()}" for step in self.steps)
        lines.extend(f"  remove {path}" for path in self.removals)
        lines.extend(f"  collision (foreign file, untouched): {path}" for path in self.collisions)
        lines.extend(f"  drifted (user-modified, not overwritten): {path}" for path in self.drifted)
        lines.extend(f"  missing (recorded but absent): {path}" for path in self.missing)
        lines.extend(f"  notice: {notice}" for notice in self.notices)
        return "\n".join(lines)


def _safe_relative(path: str) -> PurePosixPath:
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or not str(relative):
        raise SafetyError(f"refusing to plan a path outside the host directory: {path!r}")
    return relative


def disk_digest(root: Path, path: str) -> str | None:
    target = root / path
    if not target.is_file():
        return None
    return digest(target.read_bytes())


def build_install_plan(
    root: Path,
    desired: dict[str, bytes],
    ownership: Ownership | None,
    distribution_version: str,
    source: str,
    notices: tuple[str, ...] = (),
) -> Plan:
    """Plan the transition of a host directory to ``desired``.

    Targets that exist without ownership are collisions; owned files whose
    bytes no longer match the record are drift and stay untouched. Clean
    owned files and new paths are (re)written.
    """
    recorded = ownership.by_path() if ownership else {}
    steps: list[WriteStep] = []
    collisions: list[str] = []
    drifted: list[str] = []
    for path in sorted(desired):
        _safe_relative(path)
        disk = disk_digest(root, path)
        if path not in recorded and disk is not None:
            collisions.append(path)
            continue
        if path in recorded and disk is not None and disk != recorded[path]:
            drifted.append(path)
            continue
        if path in recorded and digest(desired[path]) == recorded[path]:
            continue
        steps.append(WriteStep(path=path, content=desired[path]))
    written = {
        path: digest(content)
        for path, content in desired.items()
        if path not in set(drifted) and path not in set(collisions)
    }
    ownership_after = Ownership(
        distribution_version=distribution_version,
        source=source,
        files=tuple(OwnedFile(path, sha) for path, sha in sorted(written.items())),
    )
    return Plan(
        root=root,
        steps=tuple(steps),
        removals=(),
        collisions=tuple(collisions),
        drifted=tuple(drifted),
        missing=(),
        notices=notices,
        ownership_after=ownership_after,
    )


def build_remove_plan(
    root: Path,
    ownership: Ownership,
    notices: tuple[str, ...] = (),
) -> Plan:
    """Plan the removal of exactly the files skillmate owns."""
    removals: list[str] = []
    drifted: list[str] = []
    missing: list[str] = []
    for owned in ownership.files:
        _safe_relative(owned.path)
        disk = disk_digest(root, owned.path)
        if disk is None:
            missing.append(owned.path)
        elif disk != owned.sha256:
            drifted.append(owned.path)
        else:
            removals.append(owned.path)
    return Plan(
        root=root,
        steps=(),
        removals=tuple(removals),
        collisions=(),
        drifted=tuple(drifted),
        missing=tuple(missing),
        notices=notices,
        ownership_after=None,
    )


@dataclass(frozen=True)
class ExecutionReport:
    written: tuple[str, ...]
    removed: tuple[str, ...]
    manifest: str


def execute(plan: Plan, confirmed: bool, confirm_drift: bool = False) -> ExecutionReport:
    """Apply a plan. Refuses to write anything unconfirmed or conflicted.

    Drifted files are never written or removed unless ``confirm_drift`` is
    set, matching the contracts that updates leave user drift in place and
    removals of drifted owned files need explicit confirmation.
    """
    if not confirmed:
        raise SafetyError("refusing to execute an unconfirmed plan; preview it first")
    if plan.collisions:
        raise SafetyError(
            "foreign file collisions must be resolved first: " + ", ".join(plan.collisions)
        )
    removals = list(plan.removals)
    if plan.ownership_after is None and confirm_drift:
        removals.extend(plan.drifted)
    keep_drifted = bool(plan.drifted) and plan.ownership_after is None and not confirm_drift

    plan.root.mkdir(parents=True, exist_ok=True)
    for step in plan.steps:
        target = plan.root / step.path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".skillmate-tmp")
        temporary.write_bytes(step.content)
        os.replace(temporary, target)
    for path in removals:
        target = plan.root / path
        target.unlink(missing_ok=True)
        _prune_empty_parents(plan.root, path)

    manifest_path = ""
    if plan.ownership_after is not None:
        manifest = plan.root / MANIFEST_RELATIVE
        manifest.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema": MANIFEST_SCHEMA,
            "version": plan.ownership_after.distribution_version,
            "source": plan.ownership_after.source,
            "files": [
                {"path": owned.path, "sha256": owned.sha256} for owned in plan.ownership_after.files
            ],
        }
        temporary = manifest.with_name("manifest.json.skillmate-tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, manifest)
        manifest_path = str(manifest)
    elif keep_drifted:
        # Drifted files remain on disk and stay owned; the manifest stays
        # so a later confirmed removal can still find them.
        manifest_path = str(plan.root / MANIFEST_RELATIVE)
    else:
        manifest = plan.root / MANIFEST_RELATIVE
        if manifest.is_file():
            manifest.unlink()
            _prune_empty_parents(plan.root, MANIFEST_RELATIVE)
            manifest_path = str(manifest)
    return ExecutionReport(
        written=tuple(step.path for step in plan.steps),
        removed=tuple(removals),
        manifest=manifest_path,
    )


def _prune_empty_parents(root: Path, relative: str) -> None:
    """Remove directories the removal emptied, never the host root itself."""
    current = (root / relative).parent
    while current != root and current.is_dir():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
