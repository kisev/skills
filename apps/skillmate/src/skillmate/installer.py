"""Lifecycle orchestration: sources, adapters, and plans per host.

The CLI layer resolves a source, asks the adapters for each host's desired
state, and turns it into safety-model plans. Nothing here writes: plans are
executed by :mod:`skillmate.safety` after confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

from skillmate.adapters import ADAPTERS, HostAdapter, install_notices
from skillmate.checkout import CheckoutSource
from skillmate.content import SkillContent, skill_content
from skillmate.distribution import (
    Distribution,
    DistributionError,
    RemoteSource,
    SkillArchive,
    SkillEntry,
)
from skillmate.safety import (
    Plan,
    build_install_plan,
    build_remove_plan,
    disk_digest,
    load_ownership,
)

Scope = str  # "project" | "global"


@dataclass(frozen=True)
class SourceSelection:
    """A resolved content source: the index plus an archive reader."""

    distribution: Distribution
    archive: Callable[[SkillEntry], SkillArchive]
    label: str

    def contents(self, names: tuple[str, ...] | None = None) -> tuple[SkillContent, ...]:
        selected = (
            [self.distribution.skills[name] for name in names]
            if names
            else list(self.distribution.skills.values())
        )
        return tuple(skill_content(self.archive(entry)) for entry in selected)


def resolve_source(
    from_checkout: Path | None, index_url: str, target_version: str | None
) -> SourceSelection:
    """Resolve the one source in play; no source falls back to another."""
    if from_checkout is not None:
        distribution, local = CheckoutSource(checkout=from_checkout).resolve()
        if target_version is not None:
            distribution.require_version(target_version)
        return SourceSelection(distribution=distribution, archive=local.archive, label="checkout")
    remote = RemoteSource(index_url=index_url)
    distribution = remote.index()
    if target_version is not None:
        distribution.require_version(target_version)
    return SourceSelection(distribution=distribution, archive=remote.archive, label="distribution")


def host_root(adapter: HostAdapter, scope: str, project: Path, home: Path) -> Path:
    """The directory a host reads (for example ``<project>/.claude``)."""
    if scope == "global":
        return home / adapter.skills_global.parent
    return project / adapter.skills_project.parent


def _adapters(hosts: tuple[str, ...]) -> tuple[HostAdapter, ...]:
    unknown = [host for host in hosts if host not in ADAPTERS]
    if unknown:
        raise DistributionError(f"unknown hosts: {', '.join(unknown)}")
    return tuple(ADAPTERS[host] for host in hosts)


def desired_state(
    adapter: HostAdapter, contents: tuple[SkillContent, ...], known_names: frozenset[str]
) -> dict[str, bytes]:
    """The full desired file set of one host: skills plus command surfaces."""
    desired: dict[str, bytes] = {}
    for content in contents:
        for file in adapter.materialize(content, known_names):
            desired[f"skills/{content.name}/{file.path}"] = file.data
        document = adapter.command_document(content)
        if document is not None:
            desired[f"commands/{content.name}.md"] = document.encode("utf-8")
    return desired


def plan_install(
    selection: SourceSelection,
    hosts: tuple[str, ...],
    scope: str,
    project: Path,
    home: Path,
    skill_names: tuple[str, ...] | None = None,
) -> tuple[Plan, ...]:
    """Build one install/update plan per selected host."""
    names = tuple(sorted(selection.distribution.skills)) if skill_names is None else skill_names
    missing = [name for name in names if name not in selection.distribution.skills]
    if missing:
        raise DistributionError(f"unknown skills: {', '.join(missing)}")
    contents = selection.contents(names)
    known = frozenset(selection.distribution.skills)
    notices = install_notices(hosts)
    plans: list[Plan] = []
    for adapter in _adapters(hosts):
        root = host_root(adapter, scope, project, home)
        desired = desired_state(adapter, contents, known)
        plans.append(
            build_install_plan(
                root,
                desired,
                load_ownership(root),
                selection.distribution.version,
                selection.label,
                notices=notices,
            )
        )
    return tuple(plans)


def plan_remove(
    hosts: tuple[str, ...], scope: str, project: Path, home: Path
) -> tuple[tuple[str, Plan | None], ...]:
    """Build one removal plan per selected host; ``None`` marks no install."""
    results: list[tuple[str, Plan | None]] = []
    for adapter in _adapters(hosts):
        root = host_root(adapter, scope, project, home)
        ownership = load_ownership(root)
        if ownership is None:
            results.append((adapter.host, None))
            continue
        results.append((adapter.host, build_remove_plan(root, ownership)))
    return tuple(results)


@dataclass(frozen=True)
class Diagnosis:
    """One doctor finding: what is wrong, where, and how to repair it."""

    host: str
    scope: str
    kind: str
    detail: str
    repair: str


@dataclass(frozen=True)
class InstallRecord:
    """One installed host and scope, as status reports it."""

    host: str
    scope: str
    version: str
    source: str
    files: int


def status(
    hosts: tuple[str, ...], scope: str, project: Path, home: Path
) -> tuple[InstallRecord, ...]:
    """Read the installed versions per host and scope."""
    records: list[InstallRecord] = []
    for adapter in _adapters(hosts):
        root = host_root(adapter, scope, project, home)
        ownership = load_ownership(root)
        if ownership is None:
            continue
        records.append(
            InstallRecord(
                host=adapter.host,
                scope=scope,
                version=ownership.distribution_version,
                source=ownership.source,
                files=len(ownership.files),
            )
        )
    return tuple(records)


def doctor(
    hosts: tuple[str, ...],
    scope: str,
    project: Path,
    home: Path,
    selection: SourceSelection | None,
) -> tuple[Diagnosis, ...]:
    """Diagnose each installation without writing anything.

    Names missing files, version drift against the distribution, user
    drift, stale ownership records, and foreign files occupying
    distribution paths, each with its exact repair.
    """
    diagnoses: list[Diagnosis] = []
    for adapter in _adapters(hosts):
        root = host_root(adapter, scope, project, home)
        ownership = load_ownership(root)
        if ownership is None:
            diagnoses.append(
                Diagnosis(
                    host=adapter.host,
                    scope=scope,
                    kind="not-installed",
                    detail=f"no installation recorded under {root}",
                    repair="run skillmate install",
                )
            )
            continue
        desired = None
        if selection is not None:
            try:
                contents = selection.contents()
                known = frozenset(selection.distribution.skills)
                desired = desired_state(adapter, contents, known)
            except DistributionError as error:
                diagnoses.append(
                    Diagnosis(
                        host=adapter.host,
                        scope=scope,
                        kind="source-unavailable",
                        detail=str(error),
                        repair="check network or pass --from-checkout",
                    )
                )
        for owned in ownership.files:
            disk = disk_digest(root, owned.path)
            if disk is None:
                diagnoses.append(
                    Diagnosis(
                        host=adapter.host,
                        scope=scope,
                        kind="missing-file",
                        detail=owned.path,
                        repair=f"skillmate update --hosts {adapter.host}",
                    )
                )
            elif disk != owned.sha256:
                diagnoses.append(
                    Diagnosis(
                        host=adapter.host,
                        scope=scope,
                        kind="drifted-file",
                        detail=f"{owned.path} differs from the recorded digest",
                        repair="restore it or reconfirm the change with skillmate update",
                    )
                )
        if (
            selection is not None
            and ownership.distribution_version != selection.distribution.version
        ):
            diagnoses.append(
                Diagnosis(
                    host=adapter.host,
                    scope=scope,
                    kind="version-drift",
                    detail=(
                        f"installed {ownership.distribution_version}, "
                        f"distribution {selection.distribution.version}"
                    ),
                    repair=f"skillmate update --hosts {adapter.host}",
                )
            )
        if desired is not None:
            recorded = ownership.by_path()
            stale = [path for path in recorded if path not in desired]
            if stale:
                diagnoses.append(
                    Diagnosis(
                        host=adapter.host,
                        scope=scope,
                        kind="stale-record",
                        detail=f"{len(stale)} owned files are no longer part of the distribution",
                        repair=f"skillmate update --hosts {adapter.host}",
                    )
                )
            for path in sorted(desired):
                if path in recorded or disk_digest(root, path) is None:
                    continue
                diagnoses.append(
                    Diagnosis(
                        host=adapter.host,
                        scope=scope,
                        kind="foreign-path",
                        detail=f"{path} is not owned by skillmate",
                        repair=(
                            "remove or move it away, then run "
                            f"skillmate update --hosts {adapter.host}"
                        ),
                    )
                )
    return tuple(diagnoses)
