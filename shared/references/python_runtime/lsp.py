"""Read-only host-neutral LSP applicability and state model."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


with (Path(__file__).with_name("lsp-catalog.json")).open(encoding="utf-8") as _catalog_file:
    _catalog = json.load(_catalog_file)

SERVERS = tuple(
    (item["name"], set(item["extensions"]), item["executable"], item["requirement_class"])
    for item in _catalog["servers"]
)


def detect(project: Path) -> dict[str, Any]:
    candidate = project.expanduser()
    if candidate.is_symlink():
        return {"status": "error", "error": "project must not be a symlink"}
    root = candidate.resolve()
    if not root.is_dir():
        return {"status": "error", "error": "project must be an existing non-symlink directory"}
    suffixes: set[str] = set()
    try:
        for path in root.rglob("*"):
            if any(part in {".git", "node_modules", ".venv", "dist", "build"} for part in path.parts):
                continue
            if path.is_file() and not path.is_symlink():
                suffixes.add(path.suffix.lower())
    except OSError as error:
        return {"status": "error", "error": str(error)}
    disabled = os.environ.get("OPENCODE_DISABLE_LSP_DOWNLOAD") == "true"
    servers = []
    for name, extensions, executable, requirement in SERVERS:
        applicable = bool(suffixes & extensions)
        available = shutil.which(executable) is not None
        active = False
        if not applicable:
            reason = "not-selected"
        elif disabled:
            reason = "download-disabled"
        elif not available:
            reason = "missing-dependency"
        else:
            reason = "available"
        servers.append({
            "name": name,
            "applicable": applicable,
            "active": active,
            "configured": "unknown",
            "binary_available": available,
            "runtime_status": "unknown",
            "applicability": "applicable" if applicable else "not-applicable",
            "configuration": "unknown",
            "binary": "available" if available else "missing",
            "runtime": "active" if active else "inactive",
            "requirement_class": requirement,
            "missing": [] if available else [executable],
            "reason": reason,
            "install": f"Install {executable} with your project toolchain.",
        })
    return {
        "schema_version": 1,
        "catalog_version": _catalog["catalog_version"],
        "status": "ok",
        "project": str(root),
        "download_disabled": disabled,
        "servers": servers,
    }
