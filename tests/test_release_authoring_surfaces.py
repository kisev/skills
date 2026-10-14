"""The release authoring surfaces print their contracts (decision 80/B2-B5).

The content template materializes prefilled inventory choices with the printed
field contract; description and announcement are prose asset files; a declined
illustration never invents a prompt; a stale finalize prints the one-step
rebind command; and the runbook explains its own format with full URLs.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_application_workflows import (  # type: ignore[import-not-found]
    PortableWorkflowTests as _PortableWorkflowTests,
)
from test_application_workflows import fixture_git_env

HELPERS = _PortableWorkflowTests("run_runner")
# Keep pytest from collecting the imported shared suite a second time through
# this module's namespace.
del _PortableWorkflowTests

RELEASE_CONTENT_INLINE: dict[str, Any] = {
    "title": "Prepare reliable release publication artifacts",
    "description": "### Compatibility and migration\n\n- Migration: none\n",
    "version": "1.1.0",
    "announcement": "Three verified release outcomes.",
    "illustration_prompt": "Horizontal 16:9 editorial illustration without text or logos.",
    "milestone_title": "Release 1.1.0",
    "contributors": ["Example Developer"],
    "reviewers": [],
    "illustration_style": {
        "preset": "literary",
        "reference": "A restrained technical editorial",
        "custom": None,
    },
    "work_items": [
        {
            "project_id": 19,
            "iid": 21,
            "action": "close",
            "rationale": "Delivered in this release.",
            "uncertain": False,
            "comment": None,
        },
        {
            "project_id": 19,
            "iid": 22,
            "action": "comment",
            "rationale": "Needs a release reference.",
            "uncertain": True,
            "comment": "Released in v1.1.0; follow-up remains open.",
        },
        {
            "project_id": 19,
            "iid": 23,
            "action": "no_action",
            "rationale": "Documentation reference only.",
            "uncertain": False,
            "comment": None,
        },
    ],
    "label_intent": {
        "change_type": "release",
        "workflow_state": None,
        "urgency": None,
        "impact": None,
        "compatibility": "minor",
        "origin": None,
    },
}


class ReleaseAuthoringSurfaceTests(unittest.TestCase):
    def _repository(self, root: Path) -> tuple[Path, str, str]:
        repository = root / "repository"
        repository.mkdir()
        git_env = fixture_git_env("Example Developer", "developer@example.invalid")
        for arguments in (
            ("init", "-q"),
            ("config", "commit.gpgsign", "false"),
            ("config", "tag.gpgsign", "false"),
            ("config", "user.email", "developer@example.invalid"),
            ("config", "user.name", "Example Developer"),
        ):
            subprocess.run(
                ["git", *arguments],
                cwd=repository,
                env=git_env,
                check=True,
                capture_output=True,
            )
        source = repository / "release.txt"
        source.write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "release.txt"], cwd=repository, env=git_env, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, env=git_env, check=True)
        subprocess.run(["git", "tag", "v1.0.0"], cwd=repository, env=git_env, check=True)
        base_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, env=git_env, text=True
        ).strip()
        source.write_text("base\ndirect\nassociated\n", encoding="utf-8")
        subprocess.run(
            ["git", "commit", "-qam", "add associated behavior"],
            cwd=repository,
            env=git_env,
            check=True,
        )
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, env=git_env, text=True
        ).strip()
        return repository, base_sha, head_sha

    def _environment(self, root: Path, state: Path, head_sha: str) -> dict[str, str]:
        return {
            "XDG_STATE_HOME": str(root / "state"),
            "PATH": f"{root}:{os.environ['PATH']}",
            "FAKE_GLAB_STATE": str(state),
            "FAKE_GLAB_LOG": str(root / "glab.log"),
            "FAKE_HEAD_SHA": head_sha,
            "FAKE_ASSOCIATED_SHA": head_sha,
            "FAKE_COMPONENT_DESCRIPTION": "Closes #21, follows up #22, and documents #23.",
        }

    def _prepared(self, root: Path) -> tuple[dict[str, str], str, str]:
        _repository, _base_sha, head_sha = self._repository(root)
        _glab, state = HELPERS.fake_glab(root)
        environment = self._environment(root, state, head_sha)
        target = "https://gitlab.example/group/project/-/merge_requests/7"
        prepared = HELPERS.run_runner(
            "release-prepare", "prepare", "--url", target, env=environment
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
        inventory = HELPERS.run_runner(
            "release-prepare",
            "inventory",
            "--evidence",
            evidence,
            "--repo-root",
            str(root / "repository"),
            env=environment,
        )
        self.assertEqual(inventory.returncode, 0, inventory.stderr)
        inventory_path = json.loads(inventory.stdout)["artifact_path"]
        return environment, evidence, inventory_path

    def test_content_template_materializes_prefilled_content_and_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment, evidence, inventory_path = self._prepared(root)
            result = HELPERS.run_runner(
                "release-prepare",
                "content-template",
                "--bundle",
                evidence,
                "--inventory",
                inventory_path,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            answer = json.loads(result.stdout)
            template = json.loads(Path(answer["template_path"]).read_text(encoding="utf-8"))
            # Inventory choices are machine-prefilled; the agent edits semantics.
            self.assertEqual(template["contributors"], ["Example Developer"])
            self.assertEqual(sorted(item["iid"] for item in template["work_items"]), [21, 22, 23])
            self.assertEqual(template["label_intent"]["change_type"], "release")
            self.assertEqual(template["illustration_prompt"], "")
            for asset in answer["prose_assets"]:
                self.assertTrue(Path(asset["path"]).is_file(), asset)
            contract = answer["contract"]
            self.assertIn("never read runtime sources", contract["reading_discipline"])
            self.assertEqual(contract["work_items[].action"], "one of: close, comment, no_action")
            self.assertIn("decline", contract["illustration_prompt"])
            self.assertIn("humanize", contract["prose"])
            self.assertIn("scaffold", answer["next_action"]["command"])

    def test_prose_assets_and_declined_illustration_reach_the_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment, evidence, inventory_path = self._prepared(root)
            content_dir = root / "authoring"
            content_dir.mkdir()
            (content_dir / "release-description.md").write_text(
                "### Compatibility and migration\n\n- Migration: none\n", encoding="utf-8"
            )
            (content_dir / "release-announcement.md").write_text(
                "Three verified release outcomes.", encoding="utf-8"
            )
            content = dict(RELEASE_CONTENT_INLINE)
            del content["description"]
            del content["announcement"]
            del content["illustration_prompt"]
            content["description_file"] = "release-description.md"
            content["announcement_file"] = "release-announcement.md"
            content["illustration_prompt"] = ""
            content_path = content_dir / "release-content.json"
            content_path.write_text(json.dumps(content), encoding="utf-8")
            scaffolded = HELPERS.run_runner(
                "release-prepare",
                "scaffold",
                "--bundle",
                evidence,
                "--inventory",
                inventory_path,
                "--content",
                str(content_path),
                env=environment,
            )
            self.assertEqual(scaffolded.returncode, 0, scaffolded.stderr)
            scaffold = json.loads(scaffolded.stdout)
            # B3: the declined illustration ships neither a prompt companion nor
            # an announcement attachment.
            self.assertEqual(len(scaffold["companions"]), 2)
            self.assertFalse(
                any("--attach" in json.dumps(request) for request in scaffold["requests"]),
                scaffold["requests"],
            )
            plan = json.loads(Path(str(scaffold["artifact_path"])).read_text(encoding="utf-8"))
            stored = plan["payload"]["release_content"]
            self.assertTrue(stored["illustration_prompt"].startswith("Illustration declined"))
            self.assertEqual(
                stored["description"], "### Compatibility and migration\n\n- Migration: none\n"
            )
            # B5: the prose travelled from the assets, never through authored JSON.
            self.assertNotIn("description_file", stored)
            markdown = Path(str(scaffold["markdown_path"])).read_text(encoding="utf-8")
            self.assertIn("Declined: no artwork ships with this release.", markdown)
            # C2/C3: the runbook explains itself and carries full URLs.
            self.assertIn("- Format:", markdown)
            self.assertIn("https://gitlab.example/group/project/-/issues/21", markdown)
            # The stored plan stays finalizable: companions and requests agree.
            finalized = HELPERS.run_runner(
                "release-prepare",
                "finalize",
                "--plan",
                str(scaffold["plan_path"]),
                "--expected-binding",
                str(scaffold["binding"]),
                env=environment,
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            self.assertEqual(json.loads(finalized.stdout)["status"], "ok")

    def test_stale_finalize_prints_the_one_step_rebind_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment, evidence, inventory_path = self._prepared(root)
            content_path = root / "release-content.json"
            content_path.write_text(json.dumps(RELEASE_CONTENT_INLINE), encoding="utf-8")
            scaffolded = HELPERS.run_runner(
                "release-prepare",
                "scaffold",
                "--bundle",
                evidence,
                "--inventory",
                inventory_path,
                "--content",
                str(content_path),
                env=environment,
            )
            self.assertEqual(scaffolded.returncode, 0, scaffolded.stderr)
            scaffold = json.loads(scaffolded.stdout)
            # Live drift: the collected MR state changes under the plan.
            state_path = Path(environment["FAKE_GLAB_STATE"])
            state_path.write_text("changed", encoding="utf-8")
            stale = HELPERS.run_runner(
                "release-prepare",
                "finalize",
                "--plan",
                str(scaffold["plan_path"]),
                "--expected-binding",
                str(scaffold["binding"]),
                env=environment,
            )
            self.assertEqual(stale.returncode, 2, stale.stdout)
            stale_answer = json.loads(stale.stdout)
            self.assertEqual(stale_answer["status"], "stale")
            self.assertIn("rebind_command", stale_answer)
            self.assertIn("rebind", stale_answer["rebind_command"])
            self.assertIn(
                "never re-run the prepare, inventory, scaffold", stale_answer["rebind_note"]
            )
            # B4: one invocation rebinds the plan from the recorded content.
            rebound = subprocess.run(
                shlex.split(stale_answer["rebind_command"]),
                capture_output=True,
                text=True,
                env={**os.environ, **environment},
                check=False,
            )
            self.assertEqual(rebound.returncode, 0, rebound.stderr)
            rebind_answer = json.loads(rebound.stdout)
            self.assertEqual(rebind_answer["changed"], ["object"])
            self.assertEqual(
                rebind_answer["summary"]["checks"],
                ["fresh evidence", "fresh inventory", "recorded content reused verbatim"],
            )
            self.assertNotEqual(rebind_answer["binding"], scaffold["binding"])
            self.assertEqual(rebind_answer["finalize"]["status"], "ok")
            pointer = json.loads(
                Path(str(rebind_answer["plan_pointer_path"])).read_text(encoding="utf-8")
            )
            new_plan = json.loads(Path(str(pointer["plan_path"])).read_text(encoding="utf-8"))
            self.assertEqual(
                new_plan["payload"]["release_content"],
                RELEASE_CONTENT_INLINE,
                "the recorded content moves verbatim",
            )
            # The embedded finalize checked the freshly written plan digest.
            self.assertEqual(
                rebind_answer["finalize"]["publication_plan_digest"],
                Path(str(pointer["plan_path"])).stem,
            )

    def test_content_input_refusals_name_the_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment, evidence, inventory_path = self._prepared(root)
            content_dir = root / "authoring"
            content_dir.mkdir()

            def scaffold_with(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
                path = content_dir / "content.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                completed: subprocess.CompletedProcess[str] = HELPERS.run_runner(
                    "release-prepare",
                    "scaffold",
                    "--bundle",
                    evidence,
                    "--inventory",
                    inventory_path,
                    "--content",
                    str(path),
                    env=environment,
                )
                return completed

            unknown = dict(RELEASE_CONTENT_INLINE)
            unknown["summary_file"] = "extra.md"
            refused = scaffold_with(unknown)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("unknown keys", refused.stderr)
            self.assertIn("summary_file", refused.stderr)

            (content_dir / "release-description.md").write_text("Prose.\n", encoding="utf-8")
            both = dict(RELEASE_CONTENT_INLINE)
            both["description_file"] = "release-description.md"
            both["illustration_prompt"] = None
            refused = scaffold_with(both)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("never both", refused.stderr)

            missing = dict(RELEASE_CONTENT_INLINE)
            missing["illustration_prompt"] = None
            missing["description"] = None
            missing["description_file"] = "absent-description.md"
            refused = scaffold_with(missing)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("author the file first", refused.stderr)

            declined = dict(RELEASE_CONTENT_INLINE)
            declined["illustration_prompt"] = None
            refused = scaffold_with(declined)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("never invent", refused.stderr)


if __name__ == "__main__":
    unittest.main()
