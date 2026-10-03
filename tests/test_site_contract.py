from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]

SITE = ROOT / "apps" / "docs-site"
EXAMPLES = SITE / "src" / "content" / "examples"
PILOT_SKILLS = ("askme", "code-review", "commit-msg")
SITE_RESERVED = {"index.json", "skills-lock.json", "archives", ".well-known", "dev"}


def load_module(path: Path, name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def load_examples(locale: str) -> dict[str, dict[str, Any]]:
    examples: dict[str, dict[str, Any]] = {}
    for path in sorted((EXAMPLES / locale).glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", raw, flags=re.DOTALL)
        assert match is not None, f"missing frontmatter: {path}"
        frontmatter = yaml.safe_load(match.group(1))
        assert isinstance(frontmatter, dict), f"invalid frontmatter: {path}"
        examples[path.stem] = frontmatter
    return examples


def test_examples_have_locale_parity() -> None:
    english = load_examples("en")
    russian = load_examples("ru")
    assert english, "pilot examples are missing"
    assert set(english) == set(russian), "example locales diverge"
    for name, frontmatter in english.items():
        assert frontmatter["skill"] == russian[name]["skill"], name
        assert frontmatter["order"] == russian[name]["order"], name
        assert frontmatter["title"] != russian[name]["title"], name


def test_example_frontmatter_targets_known_skills() -> None:
    known = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.source.md")}
    for locale in ("en", "ru"):
        for name, frontmatter in load_examples(locale).items():
            assert name == frontmatter["skill"], f"file name must match the skill: {name}"
            assert frontmatter["skill"] in known, f"unknown skill: {frontmatter['skill']}"
            assert isinstance(frontmatter["order"], int)
            assert len(frontmatter["prompt"]) > 0
            assert len(frontmatter["steps"]) > 0
            for step in frontmatter["steps"]:
                assert len(step["title"]) > 0
            assert len(frontmatter["artifacts"]) > 0
            for artifact in frontmatter["artifacts"]:
                assert len(artifact["label"]) > 0
                assert len(artifact["content"]) > 0
                assert len(artifact["language"]) > 0


def test_pilot_skills_have_examples_in_both_locales() -> None:
    for locale in ("en", "ru"):
        examples = load_examples(locale)
        for skill in PILOT_SKILLS:
            assert skill in examples, f"missing {locale} example for {skill}"


def test_compose_merges_site_and_rejects_reserved_collisions(tmp_path: Path) -> None:
    module = load_module(ROOT / "scripts" / "compose_pages_site.py", "compose_pages_site")

    stable = tmp_path / "stable"
    (stable / "archives").mkdir(parents=True)
    (stable / "archives" / "sha256.tar.gz").write_bytes(b"")
    (stable / "index.json").write_text("{}", encoding="utf-8")
    (stable / ".nojekyll").write_bytes(b"")
    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "index.json").write_text("{}", encoding="utf-8")
    site = tmp_path / "site"
    (site / "_astro").mkdir(parents=True)
    (site / "pagefind").mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")

    output = tmp_path / "pages"
    module.compose(
        output,
        stable_dir=stable,
        stable_url=None,
        dev_dir=dev,
        dev_url=None,
        site_dir=site,
    )
    assert (output / "index.html").is_file()
    assert (output / "index.json").is_file()
    assert (output / "archives").is_dir()
    assert (output / "dev" / "index.json").is_file()
    assert (output / ".nojekyll").read_bytes() == b""

    colliding = tmp_path / "colliding"
    colliding.mkdir()
    (colliding / "index.json").write_text("{}", encoding="utf-8")
    try:
        module.compose(
            tmp_path / "pages-colliding",
            stable_dir=stable,
            stable_url=None,
            dev_dir=dev,
            dev_url=None,
            site_dir=colliding,
        )
    except module.ComposeError as error:
        assert "collides" in str(error)
    else:
        raise AssertionError("reserved collision was accepted")

    for name in SITE_RESERVED:
        assert name not in {path.name for path in site.iterdir()}


def test_site_is_wired_into_the_task_graph_and_pages_composition() -> None:
    taskfile = (ROOT / "taskfile.yml").read_text(encoding="utf-8")
    assert "site:build" in taskfile
    assert "npm ci --prefix apps/docs-site" in taskfile
    assert "npm run build --prefix apps/docs-site" in taskfile
    assert "python scripts/check_npm_audit.py --prefix apps/docs-site" in taskfile
    compose_call = taskfile.split("pages:compose:stable:", 1)[1].split("dev:version:", 1)[0]
    assert "--site-dir apps/docs-site/dist" in compose_call
    dev_prepare = taskfile.split("dev:prepare:", 1)[1].split("dev:npm:", 1)[0]
    assert "task: site:build" in dev_prepare
    assert "--site-dir apps/docs-site/dist" in dev_prepare
    check_core = taskfile.split("check:core:", 1)[1].split("check:", 1)[0]
    assert "task: site:build" in check_core


def test_locale_manifest_declares_site_example_content() -> None:
    manifest = json.loads((ROOT / "shared" / "locale-manifest.json").read_text(encoding="utf-8"))
    declared = manifest.get("application_content")
    assert isinstance(declared, list) and declared
    globs = {entry["glob"] for entry in declared if isinstance(entry, dict) and "glob" in entry}
    assert "apps/docs-site/src/content/examples/en/*.md" in globs
    assert "apps/docs-site/src/content/examples/ru/*.md" in globs
