"""Read-only fingerprints of free-project data outside its default-branch tree."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from stand import Stand


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def pages(stand: Stand, endpoint: str) -> list[dict[str, Any]]:
    values = []
    for page in range(1, 1001):
        separator = "&" if "?" in endpoint else "?"
        items = stand.request("GET", endpoint + f"{separator}per_page=100&page={page}")
        if not isinstance(items, list):
            raise RuntimeError("Free-zone pagination returned a non-list response")
        values.extend(items)
        if len(items) < 100:
            return values
    raise RuntimeError("Free-zone evidence exceeded 1000 pages; preservation is unproven")


def snapshot(stand: Stand) -> dict[str, str]:
    prefix = f"/projects/{stand.manifest['free']['id']}"
    result = {}

    def capture(name: str, value: object) -> None:
        result[name] = digest(value)

    capture("project", stand.request("GET", prefix))
    for resource in ("labels", "milestones", "releases", "variables", "snippets", "uploads"):
        capture(resource, pages(stand, prefix + "/" + resource))
    for kind in ("issues", "merge_requests"):
        items = pages(stand, prefix + f"/{kind}?state=all")
        capture(kind, items)
        for item in items:
            endpoint = prefix + f"/{kind}/{item['iid']}"
            capture(f"{kind}/{item['iid']}/discussions", pages(stand, endpoint + "/discussions"))
            if kind == "issues":
                capture(f"issues/{item['iid']}/links", pages(stand, endpoint + "/links"))
    for kind in ("branches", "tags"):
        refs = pages(stand, prefix + "/repository/" + kind)
        capture("repository/" + kind, refs)
        for ref in refs:
            sha = ref["commit"]["id"]
            tree = pages(stand, prefix + f"/repository/tree?ref={sha}&recursive=true")
            capture(f"tree/{sha}", tree)
    wikis = pages(stand, prefix + "/wikis")
    capture("wikis", wikis)
    for wiki in wikis:
        capture(
            "wiki/" + wiki["slug"],
            stand.request("GET", prefix + "/wikis/" + quote(wiki["slug"], safe="")),
        )
    # This explicit local free directory is outside the Git repository tree.
    # Symlink targets are fingerprinted, never followed into arbitrary user files.
    free = stand.home / "free"
    if free.is_symlink():
        capture("local/free", {"symlink": str(free.readlink())})
    elif free.exists():
        for path in sorted(free.rglob("*")):
            name = "local/free/" + str(path.relative_to(free))
            if path.is_symlink():
                capture(name, {"symlink": str(path.readlink())})
            elif path.is_file():
                result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif path.is_dir():
                capture(name, {"directory": True})
            else:
                raise RuntimeError("Unsupported local free-zone object; preservation is unproven")
    return result


def verify(before: dict[str, str], after: dict[str, str]) -> None:
    changed = sorted(
        key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
    )
    if changed:
        raise RuntimeError("Free-zone fingerprints changed: " + ", ".join(changed))
