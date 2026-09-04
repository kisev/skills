from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sync_shared

ROOT = Path(__file__).resolve().parents[1]


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
    def test_askme_frontmatter_and_references(self) -> None:
        skill = ROOT / "skills/askme/SKILL.md"
        lines = skill.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "---")
        end = lines.index("---", 1)
        fields = {
            line.split(":", 1)[0]
            for line in lines[1:end]
            if line and not line.startswith(" ") and ":" in line
        }
        self.assertEqual(
            fields, {"name", "description", "license", "metadata"}
        )
        self.assertEqual(lines[1], "name: askme")
        self.assertIn("license: MIT", lines)
        self.assertIn('  author: "Kirill Sevriugin"', lines)
        self.assertIn('  version: "1.0.0"', lines)
        text = skill.read_text(encoding="utf-8")
        self.assertIn("references/question-guidelines.md", text)
        self.assertIn("Если у host нет такого инструмента, задай вопросы в чате.", text)
        self.assertIn("Если фактов достаточно", text)
        self.assertIn("`task-prepare`", text)
        self.assertNotIn("native OpenCode", text)
        self.assertNotIn("../../", text)
        self.assertNotIn("Каталог", text)
        self.assertEqual(
            (ROOT / "skills/askme/references/question-guidelines.md").read_bytes(),
            (ROOT / "shared/references/question-guidelines.md").read_bytes(),
        )

    def test_portable_skills_have_no_forbidden_dependencies(self) -> None:
        forbidden = ("../..", "~/.config/opencode", "~/.local/state/opencode", "bedrock.")
        for path in (ROOT / "skills").rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for marker in forbidden:
                    self.assertNotIn(marker, text, f"{marker} in {path}")

    def test_npx_installs_askme_into_codex_and_opencode_targets(self) -> None:
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
                "askme",
                "--agent",
                "codex",
                "--agent",
                "opencode",
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
        installed = home / ".agents/skills/askme"
        self.assertTrue((installed / "SKILL.md").is_file())
        self.assertTrue((installed / "references/question-guidelines.md").is_file())
        shutil.rmtree(checkout / "shared")
        self.assertEqual(
            (installed / "references/question-guidelines.md").read_bytes(),
            (ROOT / "skills/askme/references/question-guidelines.md").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
