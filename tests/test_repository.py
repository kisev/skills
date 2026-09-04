from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sync_shared

ROOT = Path(__file__).resolve().parents[1]
PORTABLE_SKILLS = (
    "agents-md",
    "askme",
    "commit-msg",
    "docs-prepare",
    "docs-review",
    "humanize",
    "project-spec",
    "stopit",
    "summary",
)
FORBIDDEN_PORTABLE_MARKERS = (
    "../..",
    "bedrock.",
    "catalog.yml",
    "~/.config/opencode",
    "~/.local/state/opencode",
    "opencode",
)
PROJECT_REFERENCES = (
    "references/requirements.md",
    "references/architecture.md",
    "references/interviewing.md",
    "references/onboarding.md",
    "references/consolidation.md",
    "references/adr.md",
    "references/auditing.md",
)
SPEC_TEMPLATE_READMES = (
    "templates/specs/README.md",
    "templates/specs/requirements/README.md",
    "templates/specs/requirements/functional/README.md",
    "templates/specs/requirements/interfaces/README.md",
    "templates/specs/requirements/quality/README.md",
    "templates/specs/requirements/constraints/README.md",
    "templates/specs/architecture/README.md",
    "templates/specs/architecture/01-introduction-and-goals/README.md",
    "templates/specs/architecture/02-architecture-constraints/README.md",
    "templates/specs/architecture/03-context-and-scope/README.md",
    "templates/specs/architecture/04-solution-strategy/README.md",
    "templates/specs/architecture/05-building-block-view/README.md",
    "templates/specs/architecture/06-runtime-view/README.md",
    "templates/specs/architecture/07-deployment-view/README.md",
    "templates/specs/architecture/08-crosscutting-concepts/README.md",
    "templates/specs/architecture/09-architecture-decisions/README.md",
    "templates/specs/architecture/10-quality-requirements/README.md",
    "templates/specs/architecture/11-risks-and-technical-debt/README.md",
    "templates/specs/architecture/12-glossary/README.md",
)
WORKFLOW_CONTRACTS = {
    "humanize": (
        "точные цитаты, код, вывод команд",
        "не подменяй роль автора ролью ревьюера",
    ),
    "summary": (
        "не добавляй фактов, которых нет в исходных данных",
        "строго различай текущую ситуацию, предложение, принятое решение",
    ),
    "commit-msg": (
        "git diff --cached",
        "выведи ровно одну строку",
        "не выполняй `git add`, `git commit`",
    ),
    "agents-md": (
        "до 20 однострочных пунктов",
        "покажи точный diff и получи явное подтверждение",
    ),
    "docs-prepare": (
        "один пользовательский документ diataxis",
        "покажи путь и черновик либо diff",
    ),
    "docs-review": (
        "не изменяй репозиторий, документы, внешние системы",
        "сообщай только подтверждённые замечания",
    ),
    "project-spec": (
        "пользователь должен явно передать один режим",
        "`spec-init`",
        "`spec-onboard`",
        "`spec-update`",
        "`spec-audit`",
        "все 19 обязательных `readme.md`",
        "этот режим полностью read-only",
    ),
    "stopit": (
        "во временной директории ос, не в репозитории",
        "покажи полный черновик и временный путь",
    ),
}
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


class SyncSharedTests(unittest.TestCase):
    def make_fixture(self) -> tuple[Path, Path, Path]:
        root = Path(tempfile.mkdtemp())
        shared = root / "shared"
        skills = root / "skills"
        (shared / "references").mkdir(parents=True)
        (skills / "demo").mkdir(parents=True)
        (shared / "references/source.md").write_text("source\n", encoding="utf-8")
        (shared / "manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "files": [
                        {
                            "source": "references/source.md",
                            "destination": "demo/references/result.md",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return root, shared, skills

    def run_fixture(self, root: Path, shared: Path, skills: Path, check: bool) -> int:
        with patch.object(sync_shared, "ROOT", root), patch.object(
            sync_shared, "SHARED", shared
        ), patch.object(sync_shared, "SHARED_REFERENCES", shared / "references"), patch.object(
            sync_shared, "SKILLS", skills
        ), patch.object(sync_shared, "MANIFEST", shared / "manifest.json"):
            return sync_shared.main(["--check"] if check else [])

    def test_materializes_exact_copy_and_check_is_read_only(self) -> None:
        root, shared, skills = self.make_fixture()
        self.assertEqual(self.run_fixture(root, shared, skills, False), 0)
        destination = skills / "demo/references/result.md"
        self.assertEqual(destination.read_bytes(), (shared / "references/source.md").read_bytes())
        before = destination.stat().st_mtime_ns
        self.assertEqual(self.run_fixture(root, shared, skills, True), 0)
        self.assertEqual(destination.stat().st_mtime_ns, before)

    def test_check_detects_content_and_missing_file_drift(self) -> None:
        root, shared, skills = self.make_fixture()
        self.assertEqual(self.run_fixture(root, shared, skills, False), 0)
        destination = skills / "demo/references/result.md"
        destination.write_text("drift\n", encoding="utf-8")
        self.assertNotEqual(self.run_fixture(root, shared, skills, True), 0)
        destination.unlink()
        self.assertNotEqual(self.run_fixture(root, shared, skills, True), 0)

    def test_rejects_traversal_before_writing(self) -> None:
        root, shared, skills = self.make_fixture()
        manifest = json.loads((shared / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"][0]["destination"] = "../outside.md"
        (shared / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.run_fixture(root, shared, skills, False), 2)
        self.assertFalse((root / "outside.md").exists())
        manifest["files"][0]["destination"] = "demo/references/result.md"
        manifest["files"][0]["source"] = "../outside.md"
        (shared / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.run_fixture(root, shared, skills, False), 2)
        self.assertFalse((skills / "demo/references/result.md").exists())

    def test_rejects_source_and_destination_symlinks_before_writing(self) -> None:
        root, shared, skills = self.make_fixture()
        (shared / "references/alias.md").symlink_to(shared / "references/source.md")
        manifest = json.loads((shared / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"][0]["source"] = "references/alias.md"
        (shared / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.run_fixture(root, shared, skills, False), 2)
        (shared / "references/alias.md").unlink()
        (skills / "demo/references").mkdir()
        (skills / "demo/references/alias").symlink_to(shared / "references/source.md")
        manifest["files"][0]["source"] = "references/source.md"
        manifest["files"][0]["destination"] = "demo/references/alias/result.md"
        (shared / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.run_fixture(root, shared, skills, False), 2)

    def test_rolls_back_all_destinations_after_replacement_failure(self) -> None:
        root, shared, skills = self.make_fixture()
        first_source = shared / "references/source.md"
        second_source = shared / "references/second.md"
        second_source.write_text("second before\n", encoding="utf-8")
        manifest = {
            "version": 1,
            "files": [
                {
                    "source": "references/source.md",
                    "destination": "demo/references/first.md",
                },
                {
                    "source": "references/second.md",
                    "destination": "demo/references/second.md",
                },
            ],
        }
        (shared / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.run_fixture(root, shared, skills, False), 0)
        first_destination = skills / "demo/references/first.md"
        second_destination = skills / "demo/references/second.md"
        first_before = first_destination.read_bytes()
        second_before = second_destination.read_bytes()
        first_source.write_text("first after\n", encoding="utf-8")
        second_source.write_text("second after\n", encoding="utf-8")
        replace = sync_shared.os.replace

        def fail_second_replacement(source: Path, destination: Path) -> None:
            if (
                Path(source).name == "1"
                and Path(destination) == second_destination
                and Path(source).parent.name.startswith("sync-shared-")
            ):
                raise OSError("simulated replacement failure")
            replace(source, destination)

        with patch.object(sync_shared.os, "replace", side_effect=fail_second_replacement):
            self.assertEqual(self.run_fixture(root, shared, skills, False), 2)
        self.assertEqual(first_destination.read_bytes(), first_before)
        self.assertEqual(second_destination.read_bytes(), second_before)


class PortableSkillValidationTests(unittest.TestCase):
    def test_all_portable_skills_have_required_frontmatter(self) -> None:
        for name in PORTABLE_SKILLS:
            skill = ROOT / "skills" / name / "SKILL.md"
            with self.subTest(skill=name):
                self.assertTrue(skill.is_file())
                lines = skill.read_text(encoding="utf-8").splitlines()
                self.assertEqual(lines[0], "---")
                end = lines.index("---", 1)
                fields = {
                    line.split(":", 1)[0]
                    for line in lines[1:end]
                    if line and not line.startswith(" ") and ":" in line
                }
                self.assertEqual(fields, {"name", "description", "license", "metadata"})
                self.assertEqual(lines[1], f"name: {name}")
                self.assertIn("license: MIT", lines)
                self.assertIn('  author: "Kirill Sevriugin"', lines)
                self.assertIn('  version: "1.0.0"', lines)
                metadata_start = lines.index("metadata:") + 1
                self.assertEqual(
                    lines[metadata_start:end],
                    ['  author: "Kirill Sevriugin"', '  version: "1.0.0"'],
                )

    def test_public_skill_and_repository_texts_are_russian(self) -> None:
        paths = [
            ROOT / "README.md",
            *(ROOT / "docs").rglob("*.md"),
            *(ROOT / "skills" / name / "SKILL.md" for name in PORTABLE_SKILLS),
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertRegex(path.read_text(encoding="utf-8"), CYRILLIC)
        for name in PORTABLE_SKILLS:
            lines = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8").splitlines()
            frontmatter_end = lines.index("---", 1)
            with self.subTest(skill=name, section="description"):
                self.assertRegex("\n".join(lines[1:frontmatter_end]), CYRILLIC)
            with self.subTest(skill=name, section="body"):
                self.assertRegex("\n".join(lines[frontmatter_end + 1 :]), CYRILLIC)

    def test_portable_workflows_preserve_source_contracts(self) -> None:
        for name, contracts in WORKFLOW_CONTRACTS.items():
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8").lower()
            for contract in contracts:
                with self.subTest(skill=name, contract=contract):
                    self.assertIn(contract, text)

    def test_referenced_resources_are_self_contained(self) -> None:
        resources = {
            "askme": ("references/question-guidelines.md",),
            "agents-md": ("references/agents-md-guidelines.md",),
            "project-spec": (*PROJECT_REFERENCES, "templates/adr.md", *SPEC_TEMPLATE_READMES),
        }
        for name, paths in resources.items():
            skill = ROOT / "skills" / name
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            for relative in paths:
                with self.subTest(skill=name, resource=relative):
                    self.assertTrue((skill / relative).is_file())
                    if relative.startswith("references/"):
                        self.assertIn(relative, text)

    def test_project_spec_has_complete_nineteen_file_contract(self) -> None:
        self.assertEqual(len(SPEC_TEMPLATE_READMES), 19)
        skill = ROOT / "skills/project-spec"
        self.assertTrue((skill / "templates/adr.md").is_file())
        for relative in SPEC_TEMPLATE_READMES:
            self.assertTrue((skill / relative).is_file(), relative)

    def test_askme_remains_compatible_with_portable_contract(self) -> None:
        skill = ROOT / "skills/askme/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("references/question-guidelines.md", text)
        self.assertIn("Если у host нет такого инструмента, задай вопросы в чате.", text)
        self.assertIn("Если фактов достаточно", text)
        self.assertIn("`task-prepare`", text)
        self.assertIn("Не меняй репозиторий, внешние системы, документы", text)
        self.assertIn("Не запускай отдельный workflow без нового запроса", text)
        self.assertNotIn("native OpenCode", text)
        self.assertNotIn("../../", text)
        self.assertNotIn("Каталог", text)
        self.assertEqual(
            (ROOT / "skills/askme/references/question-guidelines.md").read_bytes(),
            (ROOT / "shared/references/question-guidelines.md").read_bytes(),
        )

    def test_portable_skills_have_no_forbidden_dependencies(self) -> None:
        for path in (ROOT / "skills").rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8").lower()
                for marker in FORBIDDEN_PORTABLE_MARKERS:
                    self.assertNotIn(marker, text, f"{marker} in {path}")

    def test_npx_lists_all_portable_skills(self) -> None:
        result = subprocess.run(
            ["npx", "--yes", "skills", "add", ".", "--list"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in PORTABLE_SKILLS:
            self.assertIn(name, result.stdout)

    def test_npx_installs_each_skill_for_codex_and_opencode(self) -> None:
        for name in PORTABLE_SKILLS:
            for agent in ("codex", "opencode"):
                with self.subTest(skill=name, agent=agent):
                    self.assert_isolated_install(name, agent)

    def assert_isolated_install(self, name: str, agent: str) -> None:
        home = Path(tempfile.mkdtemp())
        checkout = home / "checkout"
        shutil.copytree(ROOT, checkout)
        environment = {
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
        }
        result = subprocess.run(
            [
                "npx",
                "--yes",
                "skills",
                "add",
                str(checkout),
                "--skill",
                name,
                "--agent",
                agent,
                "--copy",
                "--global",
                "--yes",
            ],
            cwd=checkout,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = home / ".agents/skills" / name
        self.assertTrue((installed / "SKILL.md").is_file())
        shutil.rmtree(checkout / "shared")
        shutil.rmtree(checkout)
        source = ROOT / "skills" / name
        for path in source.rglob("*"):
            if path.is_file():
                relative = path.relative_to(source)
                self.assertEqual((installed / relative).read_bytes(), path.read_bytes())


if __name__ == "__main__":
    unittest.main()
