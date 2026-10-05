from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from scripts import check_consumer_smoke as smoke

if TYPE_CHECKING:
    from pathlib import Path


def write_manifest(directory: Path, payload: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.json").write_text(json.dumps(payload), encoding="utf-8")


def write_root(root: Path, workspaces: list[str]) -> None:
    write_manifest(root, {"private": True, "workspaces": workspaces})


def package_payload(
    name: str,
    *,
    version: str = "1.0.0",
    private: bool | None = None,
    dependencies: dict[str, str] | None = None,
    peers: dict[str, str] | None = None,
    peer_meta: dict[str, Any] | None = None,
    dev: dict[str, str] | None = None,
    exports: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "version": version,
        "exports": exports
        if exports is not None
        else {".": {"types": "./dist/index.d.ts", "import": "./dist/index.js"}},
    }
    if private is not None:
        payload["private"] = private
    if dependencies is not None:
        payload["dependencies"] = dependencies
    if peers is not None:
        payload["peerDependencies"] = peers
    if peer_meta is not None:
        payload["peerDependenciesMeta"] = peer_meta
    if dev is not None:
        payload["devDependencies"] = dev
    return payload


def test_discovers_publishable_packages_from_workspaces(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/safe-fs", "packages/agentomatic", "apps/private-app"])
    write_manifest(tmp_path / "packages/safe-fs", package_payload("@x/safe-fs"))
    write_manifest(
        tmp_path / "packages/agentomatic",
        package_payload("@x/agentomatic", version="11.0.2", dependencies={"@x/safe-fs": "^1.0.0"}),
    )
    write_manifest(tmp_path / "apps/private-app", package_payload("@x/private", private=True))

    packages = smoke.ordered_packages(smoke.discover_packages(tmp_path))

    assert [(package.name, package.version) for package in packages] == [
        ("@x/safe-fs", "1.0.0"),
        ("@x/agentomatic", "11.0.2"),
    ]
    assert packages[1].workspace_dependencies == frozenset({"@x/safe-fs"})


def test_workspace_glob_patterns_expand_and_skip_non_package_dirs(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/*"])
    write_manifest(tmp_path / "packages/alpha", package_payload("@x/alpha"))
    write_manifest(tmp_path / "packages/beta", package_payload("@x/beta"))
    (tmp_path / "packages/empty").mkdir()

    packages = smoke.discover_packages(tmp_path)

    assert {package.name for package in packages} == {"@x/alpha", "@x/beta"}


def test_literal_workspace_without_manifest_fails_closed(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/ghost"])

    with pytest.raises(smoke.ConsumerSmokeError, match=r"no package\.json"):
        smoke.discover_packages(tmp_path)


def test_install_order_keeps_workspace_dependencies_before_dependents(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/safe-fs", "packages/agentomatic", "apps/memomatic"])
    write_manifest(tmp_path / "packages/safe-fs", package_payload("@x/safe-fs"))
    write_manifest(
        tmp_path / "packages/agentomatic",
        package_payload("@x/agentomatic", dependencies={"@x/safe-fs": "^1.0.0"}),
    )
    write_manifest(
        tmp_path / "apps/memomatic",
        package_payload(
            "@x/memomatic",
            dependencies={"@x/safe-fs": "^1.0.0", "@x/agentomatic": "^11.0.0"},
        ),
    )

    ordered = smoke.ordered_packages(smoke.discover_packages(tmp_path))

    assert [package.name for package in ordered] == ["@x/safe-fs", "@x/agentomatic", "@x/memomatic"]


def test_dependency_cycle_fails_closed(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/alpha", "packages/beta"])
    write_manifest(
        tmp_path / "packages/alpha", package_payload("@x/alpha", dependencies={"@x/beta": "*"})
    )
    write_manifest(
        tmp_path / "packages/beta", package_payload("@x/beta", dependencies={"@x/alpha": "*"})
    )

    with pytest.raises(smoke.ConsumerSmokeError, match="circular workspace dependencies"):
        smoke.ordered_packages(smoke.discover_packages(tmp_path))


def test_typed_export_specifiers_parse_object_string_and_subpath_forms() -> None:
    exports = {
        ".": {"types": "./dist/index.d.ts", "import": "./dist/index.js"},
        "./plugins/rules-injector": {
            "types": "./dist/plugins/rules-injector.d.ts",
            "import": "./dist/plugins/rules-injector.js",
        },
        "./package.json": "./package.json",
    }
    assert smoke.typed_export_specifiers("@x/agentomatic", exports) == (
        ".",
        "./plugins/rules-injector",
    )


def test_exports_without_a_typed_main_entry_fail_closed() -> None:
    with pytest.raises(smoke.ConsumerSmokeError, match="non-empty exports map"):
        smoke.typed_export_specifiers("@x/broken", None)
    with pytest.raises(smoke.ConsumerSmokeError, match="no typed main entry"):
        smoke.typed_export_specifiers("@x/broken", {"./util": {"types": "./dist/util.d.ts"}})


def test_wildcard_exports_fail_closed() -> None:
    with pytest.raises(smoke.ConsumerSmokeError, match="explicit entries only"):
        smoke.typed_export_specifiers("@x/broken", {"./*": {"types": "./dist/*.d.ts"}})


def test_consumer_module_imports_every_declared_entry() -> None:
    packages = [
        smoke.WorkspacePackage("packages/safe-fs", "@x/safe-fs", "1.0.0", (".",), frozenset()),
        smoke.WorkspacePackage(
            "packages/agentomatic",
            "@x/agentomatic",
            "11.0.2",
            (".", "./plugins/rules-injector"),
            frozenset({"@x/safe-fs"}),
        ),
    ]

    module = smoke.render_consumer_module(packages)

    assert 'import * as xSafeFs from "@x/safe-fs";' in module
    assert 'import * as xAgentomatic from "@x/agentomatic";' in module
    assert (
        'import * as xAgentomaticPluginsRulesInjector from "@x/agentomatic/plugins/rules-injector";'
        in module
    )
    surface = module.split("const surface: Record<string, unknown> = {", 1)[1]
    for alias in ("xSafeFs,", "xAgentomatic,", "xAgentomaticPluginsRulesInjector,"):
        assert alias in surface
    assert module.endswith("export { surface };\n")


def test_import_aliases_stay_unique_for_colliding_names() -> None:
    packages = [
        smoke.WorkspacePackage("packages/a-b", "@x/a-b", "1.0.0", (".",), frozenset()),
        smoke.WorkspacePackage("packages/a_b", "@x/a_b", "1.0.0", (".",), frozenset()),
    ]

    with pytest.raises(smoke.ConsumerSmokeError, match="aliases are not unique"):
        smoke.render_consumer_module(packages)


def test_tsconfig_pins_strict_nodenext() -> None:
    config = json.loads(smoke.render_tsconfig())

    options = config["compilerOptions"]
    assert options["module"] == "nodenext"
    assert options["moduleResolution"] == "nodenext"
    assert options["strict"] is True
    assert config["files"] == ["consumer.ts"]


def test_consumer_manifest_is_private_esm() -> None:
    assert json.loads(smoke.render_consumer_manifest()) == {"private": True, "type": "module"}


def test_explicit_packages_derive_node_types_and_optional_peers(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/safe-fs", "packages/agentomatic"])
    write_manifest(
        tmp_path / "packages/safe-fs",
        package_payload("@x/safe-fs", dev={"@types/node": "22.15.30"}),
    )
    write_manifest(
        tmp_path / "packages/agentomatic",
        package_payload(
            "@x/agentomatic",
            peers={"@x/plugin": ">=2.0.0 <2.1.0", "@x/required": "^1.0.0"},
            peer_meta={"@x/plugin": {"optional": True}},
            dev={"@x/plugin": "2.0.19"},
        ),
    )

    packages = smoke.ordered_packages(smoke.discover_packages(tmp_path))

    assert smoke.explicit_packages(packages, tmp_path) == [
        "@types/node@22.15.30",
        "@x/plugin@2.0.19",
    ]


def test_optional_peer_without_a_pinned_dev_dependency_fails_closed(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/agentomatic"])
    write_manifest(
        tmp_path / "packages/agentomatic",
        package_payload(
            "@x/agentomatic",
            peers={"@x/plugin": ">=2.0.0 <2.1.0"},
            peer_meta={"@x/plugin": {"optional": True}},
        ),
    )

    with pytest.raises(smoke.ConsumerSmokeError, match="without a pinned devDependency"):
        smoke.explicit_packages(smoke.discover_packages(tmp_path), tmp_path)


def test_missing_node_types_pin_fails_closed(tmp_path: Path) -> None:
    write_root(tmp_path, ["packages/safe-fs"])
    write_manifest(tmp_path / "packages/safe-fs", package_payload("@x/safe-fs"))

    with pytest.raises(smoke.ConsumerSmokeError, match="@types/node"):
        smoke.explicit_packages(smoke.discover_packages(tmp_path), tmp_path)
