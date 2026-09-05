"""Read-only OpenCode 1.18 LSP applicability model."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


SERVERS = (
    ("python", {".py", ".pyi"}, "basedpyright", "external-command"),
    ("typescript", {".ts", ".tsx", ".js", ".jsx"}, "typescript-language-server", "external-command"),
    ("yaml", {".yaml", ".yml"}, "yaml-language-server", "external-command"),
    ("shell", {".sh", ".bash", ".zsh"}, "bash-language-server", "external-command"),
)


def detect(project: Path) -> dict[str, Any]:
    root = project.expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        return {"status": "error", "error": "project must be an existing non-symlink directory"}
    suffixes: set[str] = set()
    try:
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                suffixes.add(path.suffix.lower())
    except OSError as error:
        return {"status": "error", "error": str(error)}
    disabled = os.environ.get("OPENCODE_DISABLE_LSP_DOWNLOAD") == "true"
    servers = []
    for name, extensions, executable, requirement in SERVERS:
        applicable = bool(suffixes & extensions)
        available = shutil.which(executable) is not None
        active = applicable and available and not disabled
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
            "requirement_class": requirement,
            "missing": [] if available else [executable],
            "reason": reason,
            "install": f"Install {executable} with your project toolchain.",
        })
    return {
        "schema_version": 1,
        "status": "ok",
        "project": str(root),
        "download_disabled": disabled,
        "servers": servers,
    }
