#!/usr/bin/env python3
"""Render CI matrix blocks and pre-push glob lists from the gate registry.

The registry (``gate-registry.json``) is the single source for gate
composition. This script rewrites only the spans between ``@gates`` markers
in ``.github/workflows/ci.yml`` and ``lefthook.yml``; the surrounding
workflow and hook skeletons stay hand-written. ``--check`` fails when any
rendered copy, the task graph, or a skeleton invariant drifts from the
registry, so every gate that runs this script also enforces the alignment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "kisev-skills/gate-registry/v1"
REGISTRY_NAME = "gate-registry.json"
TASKFILE_NAME = "taskfile.yml"
LEFTHOOK_NAME = "lefthook.yml"
CI_WORKFLOW = Path(".github") / "workflows" / "ci.yml"
CORE_KEYS = {"schema", "description", "build_precondition", "meta_triggers", "layers"}
LAYER_KEYS = {"name", "title", "task", "ci_task", "ci_job", "core", "requires_build", "paths"}


class RegistryError(Exception):
    """The registry, a rendered copy, or their consistency is invalid."""


@dataclass(frozen=True)
class Layer:
    """One gate layer: input paths bound to its gate task."""

    name: str
    title: str
    task: str
    core: bool
    requires_build: bool
    ci_task: str | None
    ci_job: str | None
    paths: tuple[str, ...]

    @property
    def matrix_task(self) -> str:
        return self.ci_task if self.ci_task is not None else self.task


@dataclass(frozen=True)
class Registry:
    """The validated registry content."""

    build_precondition: str
    meta_triggers: tuple[str, ...]
    layers: tuple[Layer, ...]

    @property
    def core_layers(self) -> tuple[Layer, ...]:
        return tuple(layer for layer in self.layers if layer.core)

    @property
    def scoped_layers(self) -> tuple[Layer, ...]:
        return tuple(layer for layer in self.layers if not layer.core)

    def matrix_layers(self, requires_build: bool) -> tuple[Layer, ...]:
        return tuple(
            layer
            for layer in self.layers
            if layer.ci_job is None and layer.requires_build is requires_build
        )


def as_string(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise RegistryError(message)
    return value


def as_optional_string(value: object, message: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise RegistryError(message)


def as_string_list(value: object, message: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RegistryError(message)
    return tuple(value)


def parse_layer(payload: object) -> Layer:
    if not isinstance(payload, dict):
        raise RegistryError("every registry layer must be an object")
    unknown = set(payload) - LAYER_KEYS
    if unknown:
        raise RegistryError(f"registry layer has unknown keys: {sorted(unknown)}")
    name = as_string(payload.get("name"), "every layer needs a string name")
    title = as_string(payload.get("title"), f"layer {name} needs a string title")
    task = as_string(payload.get("task"), f"layer {name} needs a string task")
    core = payload.get("core")
    if not isinstance(core, bool):
        raise RegistryError(f"layer {name} needs a boolean core flag")
    requires_build = payload.get("requires_build", False)
    if not isinstance(requires_build, bool):
        raise RegistryError(f"layer {name} requires_build must be a boolean")
    ci_task = as_optional_string(payload.get("ci_task"), f"layer {name} ci_task must be a string")
    ci_job = as_optional_string(payload.get("ci_job"), f"layer {name} ci_job must be a string")
    if core:
        if payload.get("paths") is not None:
            raise RegistryError(f"core layer {name} must not declare paths")
        paths: tuple[str, ...] = ()
    else:
        paths = as_string_list(payload.get("paths"), f"scoped layer {name} needs path globs")
        if not paths:
            raise RegistryError(f"scoped layer {name} needs at least one path glob")
    return Layer(name, title, task, core, requires_build, ci_task, ci_job, paths)


def parse_registry(payload: object) -> Registry:
    if not isinstance(payload, dict):
        raise RegistryError("gate-registry.json must contain an object")
    if set(payload) != CORE_KEYS:
        raise RegistryError(f"gate-registry.json keys must be exactly {sorted(CORE_KEYS)}")
    if "description" in payload:
        as_string(payload["description"], "registry description must be a string")
    schema = as_string(payload["schema"], "registry schema must be a string")
    if schema != REGISTRY_SCHEMA:
        raise RegistryError(f"registry schema must be {REGISTRY_SCHEMA}")
    precondition = as_string(
        payload["build_precondition"], "registry build_precondition must be a string"
    )
    meta_triggers = as_string_list(
        payload["meta_triggers"], "registry meta_triggers must be a list of strings"
    )
    if not meta_triggers:
        raise RegistryError("registry meta_triggers must not be empty")
    raw_layers = payload["layers"]
    if not isinstance(raw_layers, list) or not raw_layers:
        raise RegistryError("registry layers must be a non-empty list")
    layers = tuple(parse_layer(item) for item in raw_layers)
    names = [layer.name for layer in layers]
    if len(names) != len(set(names)):
        raise RegistryError("registry layer names must be unique")
    tasks = [layer.task for layer in layers]
    if len(tasks) != len(set(tasks)):
        raise RegistryError("registry layer tasks must be unique")
    if precondition in tasks:
        raise RegistryError("the build precondition is a step, not a gate layer")
    return Registry(precondition, meta_triggers, layers)


def load_registry(root: Path) -> Registry:
    path = root / REGISTRY_NAME
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"cannot read {path}: {error}") from error
    return parse_registry(payload)


def task_block(taskfile: str, task: str) -> str:
    pattern = re.compile(rf"(?ms)^  {re.escape(task)}:\n(.*?)(?=^  \S|\Z)")
    match = pattern.search(taskfile)
    if match is None:
        raise RegistryError(f"taskfile.yml has no {task} task")
    return match.group(1)


def block_tasks(block: str) -> list[str]:
    return re.findall(r"^\s*- task: (\S+)$", block, flags=re.MULTILINE)


def validate_taskfile(taskfile: str, registry: Registry) -> None:
    core_refs = block_tasks(task_block(taskfile, "check:core"))
    check_refs = block_tasks(task_block(taskfile, "check"))
    expected_core = {layer.task for layer in registry.core_layers} | {registry.build_precondition}
    if set(core_refs) != expected_core:
        raise RegistryError(
            f"check:core must reference exactly the core layers plus"
            f" {registry.build_precondition}; found {core_refs}"
        )
    precondition_position = core_refs.index(registry.build_precondition)
    for layer in registry.core_layers:
        if layer.requires_build and precondition_position > core_refs.index(layer.task):
            raise RegistryError(
                f"{registry.build_precondition} must precede {layer.task} in check:core"
            )
    expected_check = ["check:core", *(layer.task for layer in registry.scoped_layers)]
    if set(check_refs) != set(expected_check):
        raise RegistryError(
            f"check must reference exactly check:core plus the scoped layer tasks;"
            f" found {check_refs}"
        )
    if not check_refs or check_refs[0] != "check:core":
        raise RegistryError("check must run check:core before the scoped layer tasks")


def splice(text: str, key: str, rendered: str) -> str:
    pattern = re.compile(rf"(?ms)^[ ]*# @gates:begin {re.escape(key)}\n.*?^[ ]*# @gates:end$")
    match = pattern.search(text)
    if match is None:
        raise RegistryError(f"the @gates:{key} marker is missing")
    span = match.group(0)
    indent = span[: len(span) - len(span.lstrip())]
    body = "".join(f"{indent}{line}\n" for line in rendered.splitlines())
    replacement = f"{indent}# @gates:begin {key}\n{body}{indent}# @gates:end"
    return text[: match.start()] + replacement + text[match.end() :]


def render_matrix(layers: tuple[Layer, ...]) -> str:
    lines: list[str] = []
    for layer in layers:
        lines.append(f"- name: {layer.title}")
        lines.append(f"  task: {layer.matrix_task}")
    return "\n".join(lines)


def render_glob(layer: Layer, meta_triggers: tuple[str, ...]) -> str:
    return "\n".join(f'- "{path}"' for path in (*layer.paths, *meta_triggers))


def validate_ci(ci: str, registry: Registry) -> None:
    if ci.count('run: task "$CHECK_TASK"') != 2:
        raise RegistryError('both matrix jobs must execute entries through task "$CHECK_TASK"')
    for layer in registry.layers:
        if layer.ci_job is None:
            continue
        defined = re.search(rf"^  {re.escape(layer.ci_job)}:\n", ci, flags=re.MULTILINE)
        if defined is None:
            raise RegistryError(f"the handwritten {layer.ci_job} job for {layer.task} is missing")
        if f"task {layer.task}" not in ci:
            raise RegistryError(f"the handwritten job for {layer.task} must call task {layer.task}")


def pre_push_section(lefthook: str) -> str:
    parts = lefthook.split("pre-push:", 1)
    return parts[1] if len(parts) == 2 else ""


def validate_lefthook(lefthook: str, registry: Registry) -> None:
    pre_push = pre_push_section(lefthook)
    if not pre_push:
        raise RegistryError("lefthook.yml has no pre-push section")
    if "task check:core" not in pre_push:
        raise RegistryError("pre-push must always run task check:core")
    for layer in registry.scoped_layers:
        if f"task {layer.task}" not in pre_push:
            raise RegistryError(f"pre-push must run task {layer.task} for the {layer.name} layer")
    if "task pre-push" in lefthook:
        raise RegistryError("hooks must not recurse into task pre-push")


def read_gate_copies(root: Path) -> dict[Path, str]:
    paths = [root / TASKFILE_NAME, root / LEFTHOOK_NAME, root / CI_WORKFLOW]
    try:
        return {path: path.read_text(encoding="utf-8") for path in paths}
    except OSError as error:
        raise RegistryError(f"cannot read a gate copy under {root}: {error}") from error


def render(root: Path, registry: Registry) -> dict[Path, str]:
    rendered = read_gate_copies(root)
    taskfile = rendered[root / TASKFILE_NAME]
    lefthook = rendered[root / LEFTHOOK_NAME]
    ci = rendered[root / CI_WORKFLOW]

    validate_taskfile(taskfile, registry)
    validate_ci(ci, registry)
    validate_lefthook(lefthook, registry)

    ci = splice(ci, "matrix:quality", render_matrix(registry.matrix_layers(False)))
    ci = splice(ci, "matrix:built-quality", render_matrix(registry.matrix_layers(True)))
    for layer in registry.scoped_layers:
        glob = render_glob(layer, registry.meta_triggers)
        lefthook = splice(lefthook, f"glob:{layer.name}", glob)
    return {
        root / TASKFILE_NAME: taskfile,
        root / LEFTHOOK_NAME: lefthook,
        root / CI_WORKFLOW: ci,
    }


def write_atomically(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the rendered copies instead of rewriting them",
    )
    parser.add_argument("--root", type=Path, help="repository root (defaults to this checkout)")
    arguments = parser.parse_args(argv)
    root = (arguments.root or Path(__file__).resolve().parents[1]).resolve()
    try:
        registry = load_registry(root)
        rendered = render(root, registry)
    except RegistryError as error:
        print(f"gate registry drift: {error}", file=sys.stderr)
        return 1
    changed = {
        path: content
        for path, content in rendered.items()
        if path.read_text(encoding="utf-8") != content
    }
    if arguments.check:
        for path in sorted(changed):
            print(
                f"gate copy drifted from {REGISTRY_NAME}: {path.relative_to(root)}", file=sys.stderr
            )
        if changed:
            return 1
        print(f"gate copies match {REGISTRY_NAME}.")
        return 0
    for path, content in changed.items():
        write_atomically(path, content)
        print(f"rendered {path.relative_to(root)} from {REGISTRY_NAME}")
    if not changed:
        print(f"gate copies already match {REGISTRY_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
