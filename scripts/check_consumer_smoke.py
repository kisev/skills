#!/usr/bin/env python3
"""Install freshly packed workspace tarballs into a throwaway consumer and typecheck them.

The build and pack gates prove that the npm packages compile and archive; only
a real consumer project proves that a published tarball installs and
typechecks. The gate derives the publishable set from the root workspaces,
packs it after ``package:build``, installs the tarballs into one temporary
consumer project - the dependency-free foundation first, then every dependent
in a single install so they typecheck against the tested copy instead of a
registry duplicate - and runs strict ``tsc --noEmit`` with nodenext resolution
over a generated module importing every declared public entry. npm does not
install optional peer dependencies, so they are added explicitly at their
pinned devDependency version, mirroring ``registry_smoke`` in
``scripts/publish_npm_release.py``. The npm cache persists under ``.build/``
so warm runs avoid the registry round trips.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
NPM_INSTALL_FLAGS = ("--ignore-scripts", "--no-audit", "--no-fund")
NODE_TYPES_PACKAGE = "@types/node"


class ConsumerSmokeError(Exception):
    """The consumer smoke cannot prove that the tarballs install and typecheck."""


@dataclass(frozen=True)
class WorkspacePackage:
    """One publishable npm workspace and its declared public surface."""

    directory: str
    name: str
    version: str
    exports: tuple[str, ...]
    workspace_dependencies: frozenset[str]


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConsumerSmokeError(f"cannot read {path}: {error}") from error


def string_map(manifest: Mapping[str, Any], key: str, source: str) -> dict[str, str]:
    entries = manifest.get(key)
    if entries is None:
        return {}
    if not isinstance(entries, dict) or not all(
        isinstance(name, str) and isinstance(spec, str) for name, spec in entries.items()
    ):
        raise ConsumerSmokeError(f"{source} must map {key} names to string ranges")
    return dict(entries)


def typed_export_specifiers(name: str, payload: Any) -> tuple[str, ...]:
    """Return the public import specifiers that declare a types condition.

    The main entry (``.``) must be typed or the package cannot be consumed
    type-safely at all. Untyped entries such as ``./package.json`` are not
    module entries and are skipped; wildcard entries cannot be imported
    explicitly and fail instead of being silently ignored.
    """

    if not isinstance(payload, dict) or not payload:
        raise ConsumerSmokeError(f"{name} must declare a non-empty exports map")
    specifiers = []
    for key in sorted(payload):
        if "*" in key:
            raise ConsumerSmokeError(
                f"{name} exports {key!r}: the consumer smoke imports explicit entries only"
            )
        if isinstance(payload[key], dict) and isinstance(payload[key].get("types"), str):
            specifiers.append(key)
    if "." not in specifiers:
        raise ConsumerSmokeError(f"{name} exports no typed main entry ('.')")
    return tuple(specifiers)


def workspace_directories(root: Path, patterns: Any) -> list[Path]:
    if not isinstance(patterns, list) or not patterns:
        raise ConsumerSmokeError("the root package.json must declare a non-empty workspaces list")
    relatives: dict[str, None] = {}
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern:
            raise ConsumerSmokeError("every workspaces entry must be a non-empty string")
        matches = sorted(
            path
            for path in root.glob(pattern)
            if "node_modules" not in path.parts
            and path.is_dir()
            and (path / "package.json").is_file()
        )
        if not matches and not any(character in pattern for character in "*?["):
            raise ConsumerSmokeError(f"workspaces entry {pattern!r} contains no package.json")
        for path in matches:
            relatives[path.relative_to(root).as_posix()] = None
    return [root / relative for relative in relatives]


def discover_packages(root: Path) -> list[WorkspacePackage]:
    """Derive the publishable packages from the root workspaces.

    The set is never hardcoded: every workspace with ``private != true`` is a
    publishable package, in root-manifest directory order.
    """

    root_manifest = load_json(root / "package.json")
    if not isinstance(root_manifest, dict):
        raise ConsumerSmokeError("the root package.json must contain an object")
    discovered: list[WorkspacePackage] = []
    dependency_names: list[frozenset[str]] = []
    for directory in workspace_directories(root, root_manifest.get("workspaces")):
        source = directory.relative_to(root).as_posix()
        manifest = load_json(directory / "package.json")
        if not isinstance(manifest, dict):
            raise ConsumerSmokeError(f"{source}/package.json must contain an object")
        if manifest.get("private") is True:
            continue
        name, version = manifest.get("name"), manifest.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise ConsumerSmokeError(f"{source} needs string name and version to be publishable")
        exports = typed_export_specifiers(name, manifest.get("exports"))
        declared: set[str] = set()
        for section in ("dependencies", "peerDependencies", "optionalDependencies"):
            declared |= set(string_map(manifest, section, source))
        discovered.append(WorkspacePackage(source, name, version, exports, frozenset()))
        dependency_names.append(frozenset(declared))
    names = {package.name for package in discovered}
    if len(names) != len(discovered):
        raise ConsumerSmokeError("publishable workspace package names must be unique")
    return [
        replace(package, workspace_dependencies=declared & names)
        for package, declared in zip(discovered, dependency_names, strict=True)
    ]


def ordered_packages(packages: Sequence[WorkspacePackage]) -> list[WorkspacePackage]:
    """Order packages so every workspace dependency precedes its dependent."""

    remaining = {package.name: set(package.workspace_dependencies) for package in packages}
    by_name = {package.name: package for package in packages}
    ordered: list[WorkspacePackage] = []
    while remaining:
        ready = sorted(name for name, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise ConsumerSmokeError(f"circular workspace dependencies among {sorted(remaining)}")
        for name in ready:
            ordered.append(by_name[name])
            del remaining[name]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return ordered


def import_alias(name: str, specifier: str) -> str:
    raw = name if specifier == "." else f"{name} {specifier}"
    camel = "".join(part[:1].upper() + part[1:] for part in re.split(r"[^0-9a-zA-Z]+", raw) if part)
    alias = camel[:1].lower() + camel[1:]
    return alias if alias and not alias[0].isdigit() else f"package{camel}"


def render_consumer_module(packages: Sequence[WorkspacePackage]) -> str:
    lines = [
        "// Generated by scripts/check_consumer_smoke.py; do not edit.",
        "// A clean consumer must import and typecheck every declared public",
        "// entry of every publishable workspace package.",
        "",
    ]
    aliases: list[str] = []
    for package in packages:
        for specifier in package.exports:
            module = package.name if specifier == "." else f"{package.name}/{specifier[2:]}"
            alias = import_alias(package.name, specifier)
            lines.append(f'import * as {alias} from "{module}";')
            aliases.append(alias)
    if len(set(aliases)) != len(aliases):
        raise ConsumerSmokeError("generated import aliases are not unique")
    lines += [
        "",
        "// Referencing every namespace keeps the declared surface load-bearing:",
        "// tsc must resolve and typecheck each entry instead of eliding imports.",
        "const surface: Record<string, unknown> = {",
        *(f"  {alias}," for alias in aliases),
        "};",
        "",
        "export { surface };",
        "",
    ]
    return "\n".join(lines)


def render_tsconfig() -> str:
    config = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "nodenext",
            "moduleResolution": "nodenext",
            "strict": True,
            "types": ["node"],
            "skipLibCheck": True,
        },
        "files": ["consumer.ts"],
    }
    return json.dumps(config, indent=2) + "\n"


def render_consumer_manifest() -> str:
    # ``type: module`` makes nodenext resolve the imports through the packages'
    # ``import`` and ``types`` export conditions.
    return json.dumps({"private": True, "type": "module"}, indent=2) + "\n"


def explicit_packages(packages: Sequence[WorkspacePackage], root: Path) -> list[str]:
    """Derive the registry packages a consumer install must add explicitly.

    npm resolves regular dependencies from the registry and auto-installs
    required peers, but skips optional peers and never ships dev-time type
    packages, so ``@types/node`` and every devDependency-pinned optional peer
    are installed explicitly.
    """

    node_types: str | None = None
    peers: set[str] = set()
    for package in packages:
        manifest = load_json(root / package.directory / "package.json")
        if not isinstance(manifest, dict):
            raise ConsumerSmokeError(f"{package.directory}/package.json must contain an object")
        dev = string_map(manifest, "devDependencies", package.name)
        if node_types is None and NODE_TYPES_PACKAGE in dev:
            node_types = f"{NODE_TYPES_PACKAGE}@{dev[NODE_TYPES_PACKAGE]}"
        meta = manifest.get("peerDependenciesMeta")
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            raise ConsumerSmokeError(f"{package.name} peerDependenciesMeta must be an object")
        for peer in string_map(manifest, "peerDependencies", package.name):
            entry = meta.get(peer)
            if isinstance(entry, dict) and entry.get("optional") is True:
                pinned = dev.get(peer)
                if not pinned:
                    raise ConsumerSmokeError(
                        f"{package.name} declares optional peer {peer} without a pinned"
                        " devDependency; a consumer cannot typecheck it"
                    )
                peers.add(f"{peer}@{pinned}")
    if node_types is None:
        raise ConsumerSmokeError(
            f"no publishable package pins {NODE_TYPES_PACKAGE};"
            " a consumer cannot typecheck Node built-ins"
        )
    return [node_types, *sorted(peers)]


def command(*arguments: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - fixed internal tool vectors, no shell
            list(arguments), cwd=cwd, env=env, capture_output=True, text=True, check=False
        )
    except OSError as error:
        raise ConsumerSmokeError(f"cannot run {arguments[0]}: {error}") from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise ConsumerSmokeError(f"{arguments[0]} failed: {detail}")
    return result.stdout


def pack_tarball(
    root: Path, destination: Path, package: WorkspacePackage, env: dict[str, str]
) -> str:
    output = command(
        "npm",
        "pack",
        "--ignore-scripts",
        "--pack-destination",
        str(destination),
        # An explicit path argument keeps npm from parsing the directory as a
        # registry or hosted-git spec.
        str(root / package.directory),
        cwd=root,
        env=env,
    )
    filename = output.strip().splitlines()[-1].strip() if output.strip() else ""
    if not filename.endswith(".tgz") or not (destination / filename).is_file():
        raise ConsumerSmokeError(f"npm pack {package.name} produced no tarball: {output.strip()!r}")
    return filename


def run(root: Path) -> dict[str, Any]:
    timings: dict[str, float] = {}
    started = time.monotonic()

    def step(name: str, began: float) -> float:
        timings[name] = round(time.monotonic() - began, 2)
        return time.monotonic()

    packages = ordered_packages(discover_packages(root))
    began = step("discover", started)
    print(
        f"consumer smoke: publishable packages: {', '.join(package.name for package in packages)}",
        file=sys.stderr,
        flush=True,
    )
    extras = explicit_packages(packages, root)
    cache = root / ".build" / "consumer-smoke" / "npm-cache"
    tarballs_dir = root / ".build" / "consumer-smoke" / "tarballs"
    cache.mkdir(parents=True, exist_ok=True)
    tarballs_dir.mkdir(parents=True, exist_ok=True)
    # Stale tarballs from earlier runs must never satisfy an install.
    for stale in tarballs_dir.glob("*.tgz"):
        stale.unlink()
    env = {**os.environ, "NPM_CONFIG_CACHE": str(cache)}
    tarballs = {
        package.name: pack_tarball(root, tarballs_dir, package, env) for package in packages
    }
    began = step("pack", began)
    foundation, dependents = packages[0], packages[1:]
    with tempfile.TemporaryDirectory(prefix="skills-consumer-smoke-") as temporary:
        consumer = Path(temporary)
        (consumer / "package.json").write_text(render_consumer_manifest(), encoding="utf-8")
        command(
            "npm",
            "install",
            *NPM_INSTALL_FLAGS,
            str(tarballs_dir / tarballs[foundation.name]),
            cwd=consumer,
            env=env,
        )
        began = step("install_foundation", began)
        command(
            "npm",
            "install",
            *NPM_INSTALL_FLAGS,
            *(str(tarballs_dir / tarballs[package.name]) for package in dependents),
            *extras,
            cwd=consumer,
            env=env,
        )
        began = step("install_dependents", began)
        (consumer / "consumer.ts").write_text(render_consumer_module(packages), encoding="utf-8")
        (consumer / "tsconfig.json").write_text(render_tsconfig(), encoding="utf-8")
        command("tsc", "--project", "tsconfig.json", "--noEmit", cwd=consumer, env=env)
        began = step("typecheck", began)
        modules = "; ".join(
            f'await import("{module}")'
            for package in packages
            for module in (
                package.name if specifier == "." else f"{package.name}/{specifier[2:]}"
                for specifier in package.exports
            )
        )
        command("node", "--input-type=module", "--eval", modules, cwd=consumer, env=env)
        step("import", began)
        total = round(time.monotonic() - started, 2)
    return {
        "status": "ok",
        "packages": [
            {
                "name": package.name,
                "version": package.version,
                "directory": package.directory,
                "exports": list(package.exports),
                "tarball": tarballs[package.name],
            }
            for package in packages
        ],
        "explicit_packages": extras,
        "npm_cache": str(cache),
        "timings_seconds": timings,
        "total_seconds": total,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root (defaults to this checkout)")
    arguments = parser.parse_args(argv)
    try:
        report = run((arguments.root or ROOT).resolve())
    except ConsumerSmokeError as error:
        print(f"consumer smoke failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
