from __future__ import annotations

import io
import importlib.util
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import patch
from contextlib import nullcontext, redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
BUILT_SKILLS = ROOT / ".build" / "skills"
GITLAB_RUNNERS = {
    "mr-prepare": "scripts/prepare_mr.py",
    "code-review": "scripts/review_mr.py",
    "release-prepare": "scripts/prepare_release.py",
    "release-review": "scripts/review_release.py",
}


def load_module(path: Path, name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class PortableWorkflowTests(unittest.TestCase):
    def run_runner(
        self,
        skill: str,
        *arguments: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(BUILT_SKILLS / skill / GITLAB_RUNNERS[skill]),
                *arguments,
            ],
            cwd=cwd or Path(tempfile.gettempdir()),
            env={**os.environ, "PYTHONPATH": "/invalid", **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )

    def fake_glab(self, directory: Path) -> tuple[Path, Path]:
        state = directory / "fake-glab-state"
        state.write_text("fresh", encoding="utf-8")
        executable = directory / "glab"
        executable.write_text(
            """#!%s
import json
import os
import sys
from pathlib import Path

endpoint = sys.argv[-1]
Path(os.environ["FAKE_GLAB_LOG"]).open("a", encoding="utf-8").write(json.dumps(sys.argv[1:]) + "\\n")
changed = Path(os.environ["FAKE_GLAB_STATE"]).read_text(encoding="utf-8") == "changed"
head_sha = os.environ.get("FAKE_HEAD_SHA", "c")
base_sha = os.environ.get("FAKE_BASE_SHA", "a")
start_sha = os.environ.get("FAKE_START_SHA", "b")
changed_path = os.environ.get("FAKE_CHANGED_PATH")
if endpoint.startswith("projects/group%%2Fproject"):
    value = {"id": 19}
elif endpoint.startswith("projects/19/labels"):
    value = [{"name": "ship-ready", "description": "semantic-role: change_type; semantic-value: release"}, {"name": "next-compatible", "description": "semantic-role: compatibility; semantic-value: minor"}]
elif endpoint == "projects/19/merge_requests/7":
    value = {"iid": 7, "title": "Current merge request title", "description": "Current description", "source_branch": "dev", "target_branch": "main", "web_url": "https://gitlab.example/group/project/-/merge_requests/7", "author": {"username": os.environ.get("FAKE_AUTHOR_USER", "author")}, "state": os.environ.get("FAKE_MR_STATE", "opened"), "merged_at": "2026-01-02T00:00:00Z" if os.environ.get("FAKE_MR_STATE") == "merged" else None, "updated_at": "changed" if changed else "fresh", "labels": [], "diff_refs": {"base_sha": base_sha, "start_sha": start_sha, "head_sha": head_sha}}
elif endpoint == "projects/19/merge_requests/7/changes":
    value = {"changes": [{"old_path": changed_path, "new_path": changed_path}] if changed_path else [], "diff_refs": {"base_sha": base_sha, "start_sha": start_sha, "head_sha": head_sha}}
elif endpoint.startswith("projects/19/merge_requests/7/commits"):
    value = [{"id": head_sha}]
elif "/repository/commits/" in endpoint and "/merge_requests?" in endpoint:
    sha = endpoint.split("/repository/commits/", 1)[1].split("/", 1)[0]
    value = [{"id": 107, "iid": 17, "title": "Associated change", "description": "Component MR", "labels": ["type::feature"], "author": {"username": "developer"}, "web_url": "https://gitlab.example/group/project/-/merge_requests/17", "source_branch": "feature", "target_branch": "dev", "merge_commit_sha": None, "squash_commit_sha": sha, "merged_at": "2026-01-02T00:00:00Z", "state": "merged"}] if sha == os.environ.get("FAKE_ASSOCIATED_SHA") else []
elif "/repository/tags/" in endpoint:
    value = {"name": endpoint.rsplit("/", 1)[-1], "created_at": "2026-01-01T00:00:00Z", "commit": {"created_at": "2026-01-01T00:00:00Z"}}
elif endpoint == "user":
    value = {"username": os.environ.get("FAKE_CURRENT_USER", "reviewer")}
elif endpoint.startswith("projects/19/merge_requests/7/discussions"):
    value = [{"id": "discussion-42", "notes": [{"id": 42, "system": False, "resolvable": True, "resolved": False, "author": {"username": "other-reviewer"}, "body": "Retry needs an idempotency key", "position": {"head_sha": head_sha, "new_path": changed_path, "new_line": 2}}]}] if os.environ.get("FAKE_DISCUSSION") else []
elif endpoint.startswith("projects/19/merge_requests/7/notes"):
    value = []
else:
    value = []
print(json.dumps(value))
"""
            % sys.executable,
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable, state

    def test_gitlab_runners_support_foreign_cwd_help_and_capabilities(self) -> None:
        for skill in GITLAB_RUNNERS:
            with self.subTest(skill=skill, command="help"):
                self.assertEqual(self.run_runner(skill, "--help").returncode, 0)
            with self.subTest(skill=skill, command="capabilities"):
                result = self.run_runner(skill, "--capabilities")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["schema_version"], 1)

    def test_invalid_target_is_rejected_before_external_collection(self) -> None:
        for skill in GITLAB_RUNNERS:
            with self.subTest(skill=skill):
                result = self.run_runner(
                    skill, "prepare", "--url", "https://gitlab.example/group/project/-/issues"
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_input")

    def test_invalid_runner_syntax_uses_json_error_contract(self) -> None:
        for skill in GITLAB_RUNNERS:
            with self.subTest(skill=skill):
                result = self.run_runner(skill, "prepare")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "error")

    def test_mr_prepare_plan_binds_evidence_and_markdown_companion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _glab, state = self.fake_glab(root)
            log = root / "glab.log"
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(log),
            }
            target = "https://gitlab.example/group/project/-/merge_requests/7"
            batch = self.run_runner(
                "mr-prepare", "prepare", "--url", target, "--url", target, env=environment
            )
            self.assertEqual(batch.returncode, 2)
            self.assertFalse(log.exists())

            prepared = self.run_runner("mr-prepare", "prepare", "--url", target, env=environment)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
            content = root / "content.json"
            content.write_text(
                json.dumps(
                    {
                        "title": "Prepare exact merge request publication plan",
                        "description": "Proposed description",
                        "label_intent": {
                            "change_type": None,
                            "workflow_state": None,
                            "urgency": None,
                            "impact": None,
                            "compatibility": None,
                            "origin": None,
                        },
                    }
                ),
                encoding="utf-8",
            )
            scaffolded = self.run_runner(
                "mr-prepare",
                "scaffold",
                "--bundle",
                evidence,
                "--content",
                str(content),
                env=environment,
            )
            self.assertEqual(scaffolded.returncode, 0, scaffolded.stderr)
            scaffold = json.loads(scaffolded.stdout)
            plan = scaffold["artifact_path"]
            markdown = Path(scaffold["markdown_path"])
            markdown_text = markdown.read_text(encoding="utf-8")
            self.assertIn("- Decision: `change`", markdown_text)
            self.assertIn("Pipeline status for exact head SHA: `missing`", markdown_text)
            self.assertEqual(markdown.stat().st_mode & 0o777, 0o600)

            finalized = self.run_runner("mr-prepare", "finalize", "--plan", plan, env=environment)
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            self.assertEqual(
                json.loads(finalized.stdout)["result"]["publication_plan_digest"],
                scaffold["digest"],
            )

            state.write_text("changed", encoding="utf-8")
            refreshed = self.run_runner("mr-prepare", "prepare", "--url", target, env=environment)
            self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
            stale = self.run_runner("mr-prepare", "finalize", "--plan", plan, env=environment)
            self.assertEqual(stale.returncode, 2)
            self.assertEqual(json.loads(stale.stdout)["status"], "stale")

            state.write_text("fresh", encoding="utf-8")
            markdown.write_text("modified", encoding="utf-8")
            modified = self.run_runner("mr-prepare", "finalize", "--plan", plan, env=environment)
            self.assertEqual(modified.returncode, 2)
            self.assertEqual(json.loads(modified.stdout)["status"], "error")

    def test_release_prepare_inventory_artifacts_and_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            for arguments in (
                ("init", "-q"),
                ("config", "user.email", "developer@example.invalid"),
                ("config", "user.name", "Example Developer"),
            ):
                subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
            source = repository / "release.txt"
            source.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "release.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            subprocess.run(["git", "tag", "v1.0.0"], cwd=repository, check=True)
            source.write_text("base\ndirect\n", encoding="utf-8")
            subprocess.run(
                ["git", "commit", "-qam", "fix direct behavior"], cwd=repository, check=True
            )
            source.write_text("base\ndirect\nassociated\n", encoding="utf-8")
            subprocess.run(
                ["git", "commit", "-qam", "add associated behavior"], cwd=repository, check=True
            )
            head_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()

            _glab, state = self.fake_glab(root)
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(root / "glab.log"),
                "FAKE_HEAD_SHA": head_sha,
                "FAKE_ASSOCIATED_SHA": head_sha,
            }
            target = "https://gitlab.example/group/project/-/merge_requests/7"
            prepared = self.run_runner(
                "release-prepare", "prepare", "--url", target, env=environment
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
            inventory_result = self.run_runner(
                "release-prepare",
                "inventory",
                "--evidence",
                evidence,
                "--repo-root",
                str(repository),
                env=environment,
            )
            self.assertEqual(inventory_result.returncode, 0, inventory_result.stderr)
            inventory = json.loads(inventory_result.stdout)
            self.assertEqual(inventory["previous_ref"], "v1.0.0")
            self.assertEqual(
                inventory["counts"],
                {
                    "commits": 2,
                    "merge_requests": 1,
                    "direct_commits": 1,
                    "errors": 0,
                    "warnings": 0,
                },
            )

            content = root / "release-content.json"
            content.write_text(
                json.dumps(
                    {
                        "title": "Prepare reliable release publication artifacts",
                        "description": "### Compatibility and migration\n\n- Migration: none\n",
                        "version": "1.1.0",
                        "announcement": "Three verified release outcomes.",
                        "illustration_prompt": "Horizontal 16:9 editorial illustration without text or logos.",
                        "label_intent": {
                            "change_type": "release",
                            "workflow_state": None,
                            "urgency": None,
                            "impact": None,
                            "compatibility": "minor",
                            "origin": None,
                        },
                    }
                ),
                encoding="utf-8",
            )
            scaffolded = self.run_runner(
                "release-prepare",
                "scaffold",
                "--bundle",
                evidence,
                "--inventory",
                inventory["artifact_path"],
                "--content",
                str(content),
                env=environment,
            )
            self.assertEqual(scaffolded.returncode, 0, scaffolded.stderr)
            scaffold = json.loads(scaffolded.stdout)
            self.assertEqual(len(scaffold["companions"]), 3)
            self.assertTrue(all(Path(item["path"]).is_file() for item in scaffold["companions"]))
            plan = scaffold["artifact_path"]
            plan_payload = json.loads(Path(plan).read_text(encoding="utf-8"))["payload"]
            self.assertEqual(plan_payload["label_review"]["add"], ["ship-ready", "next-compatible"])
            finalized = self.run_runner(
                "release-prepare", "finalize", "--plan", plan, env=environment
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)

            subprocess.run(["git", "tag", "v1.1.0"], cwd=repository, check=True)
            stale = self.run_runner("release-prepare", "finalize", "--plan", plan, env=environment)
            self.assertEqual(stale.returncode, 2, stale.stderr)
            self.assertIn("release_inventory", json.loads(stale.stdout)["result"]["changed"])
            subprocess.run(["git", "tag", "-d", "v1.1.0"], cwd=repository, check=True)

            companion = Path(scaffold["companions"][0]["path"])
            companion.write_text("modified", encoding="utf-8")
            modified = self.run_runner(
                "release-prepare", "finalize", "--plan", plan, env=environment
            )
            self.assertEqual(modified.returncode, 2)
            self.assertEqual(json.loads(modified.stdout)["status"], "error")

    @unittest.skip("GitLab task adapter removed in stage 17")
    def test_pagination_deduplicates_and_preserves_partial_failure(self) -> None:
        module = load_module(
            BUILT_SKILLS / "task-triage/scripts/portable_runtime/contract.py",
            "portable_gitlab_contract",
        )
        pages = [list(range(100)), [99, 100]]
        with patch.object(module, "glab_json", side_effect=pages):
            result = module.paginated("gitlab.example", "projects/1/labels")
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["items"]), 101)
        with patch.object(
            module, "glab_json", side_effect=module.WorkflowError("temporary failure")
        ):
            partial = module.paginated("gitlab.example", "projects/1/labels")
        self.assertFalse(partial["complete"])
        self.assertTrue(partial["errors"])

    @unittest.skip("GitLab task adapter removed in stage 17")
    def test_collection_calls_only_get_and_batch_failure_is_isolated(self) -> None:
        module = load_module(
            BUILT_SKILLS / "task-triage/scripts/portable_runtime/contract.py", "portable_gitlab_get"
        )
        calls: list[tuple[str, str]] = []
        target = {
            "url": "https://gitlab.example/group/project/-/issues/7",
            "hostname": "gitlab.example",
            "project_path": "group/project",
            "kind": "issues",
            "iid": 7,
        }

        def fake(hostname: str, endpoint: str) -> object:
            calls.append((hostname, endpoint))
            if endpoint.startswith("projects/group%2Fproject"):
                return {"id": 1}
            if endpoint == "projects/1/issues/7":
                return {"iid": 7, "updated_at": "2026-01-01T00:00:00Z", "labels": []}
            return []

        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"XDG_STATE_HOME": temporary}):
                with patch.object(module, "glab_json", side_effect=fake):
                    bundle = module.collect(target, "task-triage")
        self.assertTrue(bundle["retrieval_complete"])
        self.assertTrue(bundle["discussions"]["complete"])
        self.assertTrue(calls)
        self.assertTrue(all("projects/" in endpoint for _, endpoint in calls))

    @unittest.skip("GitLab task adapter removed in stage 17")
    def test_gitlab_read_only_prepare_returns_compact_artifact_without_confirmation(self) -> None:
        module = load_module(
            BUILT_SKILLS / "task-triage/scripts/portable_runtime/contract.py",
            "portable_gitlab_preview",
        )

        def fake(hostname: str, endpoint: str) -> object:
            if endpoint.startswith("projects/group%2Fproject"):
                return {"id": 1}
            if endpoint.startswith("projects/1/labels"):
                return []
            if endpoint == "projects/1/issues/7":
                return {"iid": 7, "updated_at": "2026-01-01T00:00:00Z", "labels": []}
            if endpoint.startswith("projects/1/issues/7/discussions"):
                return []
            return []

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {"XDG_STATE_HOME": temporary}),
            patch.object(module, "glab_json", side_effect=fake),
            redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = module.run(
                "task-triage",
                {"issues"},
                ["prepare", "--url", "https://gitlab.example/group/project/-/issues/7"],
            )
            payload = json.loads(output.getvalue())
            artifact_exists = Path(str(payload["items"][0]["artifact_path"])).is_file()
        self.assertEqual(exit_code, 0)
        item = payload["items"][0]
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(artifact_exists)
        self.assertEqual(len(str(item["digest"])), 64)
        self.assertEqual(
            payload["summary"]["tldr"], "Completed GET-only GitLab evidence preparation."
        )
        self.assertNotIn("confirmation", payload)

    def test_publication_plan_uses_english_human_prose(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py",
            "portable_gitlab_publication_prose",
        )
        markdown = module.publication_markdown(
            {
                "target": {"url": "https://gitlab.example/group/project/-/issues/7"},
                "base_sha": None,
                "start_sha": None,
                "head_sha": None,
                "retrieval_complete": False,
            },
            {"title": "Title", "description": "Description"},
        )
        self.assertIn("# Verified publication plan", markdown)
        self.assertIn("- Collection completeness: partial", markdown)
        self.assertIn("## Proposed text", markdown)
        self.assertIn("### Title\n\nTitle", markdown)
        self.assertIn("### Description\n\nDescription", markdown)
        self.assertNotRegex(markdown, r"[А-Яа-яЁё]")

    def test_semantic_label_review_uses_catalog_meaning_not_fixed_names(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py",
            "portable_gitlab_label_semantics",
        )
        bundle = {
            "object": {
                "labels": ["team-owned", "kind/feature", "legacy release"],
            },
            "labels": {
                "items": [
                    {"name": "team-owned", "description": "Team routing"},
                    {"name": "kind/feature", "description": None},
                    {"name": "legacy release", "description": None},
                    {
                        "name": "customer-defect",
                        "description": "semantic-role: change_type; semantic-value: bug",
                    },
                    {"name": "risk/high", "description": None},
                    {
                        "name": "compatible-fix",
                        "description": "semantic-role=compatibility; semantic-value=patch",
                    },
                ],
                "complete": True,
            },
        }
        intent = {
            "change_type": "bug",
            "workflow_state": None,
            "urgency": None,
            "impact": "high",
            "compatibility": "patch",
            "origin": "external",
        }
        result = module.review_labels(bundle, intent)

        self.assertTrue(result["complete"])
        self.assertEqual(result["add"], ["customer-defect", "risk/high", "compatible-fix"])
        self.assertEqual(result["remove"], ["kind/feature"])
        self.assertEqual(
            result["proposed"],
            ["team-owned", "legacy release", "customer-defect", "risk/high", "compatible-fix"],
        )
        self.assertIn("legacy release", result["proposed"])
        origin = next(item for item in result["decisions"] if item["role"] == "origin")
        self.assertEqual(origin["action"], "unsupported")

        ambiguous = json.loads(json.dumps(bundle))
        ambiguous["labels"]["items"].append(
            {
                "name": "another-defect",
                "description": "semantic-role: change_type; semantic-value: bug",
            }
        )
        unresolved = module.review_labels(ambiguous, intent)
        self.assertFalse(unresolved["complete"])
        self.assertNotIn("customer-defect", unresolved["add"])
        self.assertNotIn("kind/feature", unresolved["remove"])

    @unittest.skip("GitLab task adapter removed in stage 17")
    def test_glab_boundary_forces_get_without_shell_or_credentials(self) -> None:
        module = load_module(
            BUILT_SKILLS / "task-triage/scripts/portable_runtime/contract.py",
            "portable_gitlab_boundary",
        )
        completed = SimpleNamespace(returncode=0, stdout="{}", stderr="token=hidden")
        with patch.object(module.shutil, "which", return_value="/fake/glab"):
            with patch.object(module.subprocess, "run", return_value=completed) as run:
                self.assertEqual(module.glab_json("gitlab.example", "projects/1"), {})
        command = run.call_args.args[0]
        self.assertIn("GET", command)
        self.assertNotIn("hidden", " ".join(command))
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_code_review_requires_real_independent_critic_capability(self) -> None:
        result = self.run_runner("code-review", "assess-mode", "--mode", "deep")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(json.loads(result.stdout)["status"], "unsupported")

    def test_local_review_finalization_rejects_changed_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            for arguments in (
                ("init", "-q"),
                ("config", "user.email", "test@example.invalid"),
                ("config", "user.name", "Test"),
            ):
                subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
            source = repository / "sample.txt"
            source.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-qm", "base"], cwd=repository, check=True, capture_output=True
            )
            source.write_text("first\n", encoding="utf-8")
            environment = {"XDG_STATE_HOME": str(repository / "state")}
            prepared = self.run_runner(
                "code-review",
                "prepare-local",
                "--repo-root",
                str(repository),
                cwd=repository,
                env=environment,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            bundle = json.loads(prepared.stdout)["bundle"]
            source.write_text("second\n", encoding="utf-8")
            finalized = self.run_runner(
                "code-review", "finalize-local", "--bundle", bundle, cwd=repository, env=environment
            )
            self.assertEqual(finalized.returncode, 2)
            self.assertEqual(json.loads(finalized.stdout)["status"], "stale")

    def test_local_finalize_detects_each_committed_and_wip_section(self) -> None:
        for section in ("committed", "staged", "unstaged", "untracked"):
            with self.subTest(section=section), tempfile.TemporaryDirectory() as temporary:
                repository = Path(temporary)
                for git_arguments in (
                    ("init", "-q"),
                    ("config", "user.email", "test@example.invalid"),
                    ("config", "user.name", "Test"),
                ):
                    subprocess.run(
                        ["git", *git_arguments], cwd=repository, check=True, capture_output=True
                    )
                source = repository / "sample.txt"
                source.write_text("base\n", encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-qm", "base"],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                )
                if section == "committed":
                    source.write_text("first\n", encoding="utf-8")
                    subprocess.run(
                        ["git", "commit", "-am", "first"],
                        cwd=repository,
                        check=True,
                        capture_output=True,
                    )
                environment = {"XDG_STATE_HOME": str(repository / "state")}
                arguments: list[str] = ["prepare-local", "--repo-root", str(repository)]
                if section == "committed":
                    arguments.extend(("--ref", "HEAD~1"))
                prepared = self.run_runner(
                    "code-review", *arguments, cwd=repository, env=environment
                )
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                bundle = json.loads(prepared.stdout)["bundle"]
                if section == "committed":
                    source.write_text("second\n", encoding="utf-8")
                    subprocess.run(
                        ["git", "commit", "-am", "second"],
                        cwd=repository,
                        check=True,
                        capture_output=True,
                    )
                elif section == "staged":
                    source.write_text("staged\n", encoding="utf-8")
                    subprocess.run(
                        ["git", "add", "sample.txt"],
                        cwd=repository,
                        check=True,
                        capture_output=True,
                    )
                elif section == "unstaged":
                    source.write_text("unstaged\n", encoding="utf-8")
                else:
                    (repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")
                finalized = self.run_runner(
                    "code-review",
                    "finalize-local",
                    "--bundle",
                    bundle,
                    cwd=repository,
                    env=environment,
                )
                self.assertEqual(finalized.returncode, 2)
                self.assertEqual(json.loads(finalized.stdout)["status"], "stale")

    def test_local_wip_keeps_staged_unstaged_and_untracked_without_following_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            for arguments in (
                ("init", "-q"),
                ("config", "user.email", "test@example.invalid"),
                ("config", "user.name", "Test"),
            ):
                subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
            tracked = repository / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "tracked.txt"], cwd=repository, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-qm", "base"], cwd=repository, check=True, capture_output=True
            )
            tracked.write_text("committed\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "tracked.txt"], cwd=repository, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-qm", "committed"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            tracked.write_text("staged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "tracked.txt"], cwd=repository, check=True, capture_output=True
            )
            tracked.write_text("unstaged\n", encoding="utf-8")
            (repository / "note.txt").write_text("untracked\n", encoding="utf-8")
            (repository / "linked.txt").symlink_to(repository / "note.txt")
            (repository / "binary.bin").write_bytes(b"\0binary")
            oversized = repository / "oversized.txt"
            oversized.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
            environment = {"XDG_STATE_HOME": str(repository / "state")}
            prepared = self.run_runner(
                "code-review",
                "prepare-local",
                "--repo-root",
                str(repository),
                "--ref",
                "HEAD~1",
                cwd=repository,
                env=environment,
            )
            self.assertEqual(prepared.returncode, 2, prepared.stderr)
            payload = json.loads(prepared.stdout)
            self.assertEqual(payload["status"], "incomplete")
            module = load_module(
                BUILT_SKILLS / "code-review/scripts/portable_runtime/contract.py",
                "portable_local_sections",
            )
            _, bundle = module.artifact_payload(Path(payload["bundle"]), "local_wip_snapshot")
            sections = bundle["sections"]
            self.assertIn("staged", sections["staged"]["diff"])
            self.assertIn("unstaged", sections["unstaged"]["diff"])
            self.assertIn("committed", sections["committed"]["diff"])
            linked = next(
                item for item in sections["untracked"]["items"] if item["path"] == "linked.txt"
            )
            self.assertEqual(linked["reason"], "symlink")
            binary = next(
                item for item in sections["untracked"]["items"] if item["path"] == "binary.bin"
            )
            self.assertEqual(binary["reason"], "binary")
            too_large = next(
                item for item in sections["untracked"]["items"] if item["path"] == "oversized.txt"
            )
            self.assertEqual(too_large["reason"], "oversized")

    def test_local_wip_marks_unreadable_untracked_evidence_incomplete(self) -> None:
        module = load_module(
            BUILT_SKILLS / "code-review/scripts/portable_runtime/contract.py",
            "portable_local_unreadable",
        )
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True, capture_output=True)
            unavailable = repository / "unreadable.txt"
            unavailable.write_text("unreadable\n", encoding="utf-8")
            original = Path.read_bytes

            def read_bytes(path: Path) -> bytes:
                if path == unavailable:
                    raise OSError("permission denied")
                return original(path)

            with patch.object(Path, "read_bytes", read_bytes):
                result = module.local_untracked(repository)
        self.assertFalse(result["complete"])
        self.assertEqual(
            result["items"], [{"path": "unreadable.txt", "complete": False, "reason": "unreadable"}]
        )

    def test_collection_identity_is_shared_and_issue_discussions_are_required(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py", "canonical_gitlab_identity"
        )
        target = {
            "url": "https://gitlab.example/group/project/-/issues/7",
            "hostname": "gitlab.example",
            "project_path": "group/project",
            "kind": "issues",
            "iid": 7,
        }
        calls: list[str] = []

        def fake(_hostname: str, endpoint: str) -> object:
            calls.append(endpoint)
            if endpoint.startswith("projects/group%2Fproject"):
                return {"id": 19}
            if endpoint == "projects/19/issues/7":
                return {"iid": 7, "labels": [], "updated_at": "2026-01-01T00:00:00Z"}
            if endpoint.startswith("projects/19/issues/7/discussions"):
                raise module.WorkflowError("page unavailable")
            return []

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {"XDG_STATE_HOME": temporary}),
            patch.object(module, "glab_json", side_effect=fake),
        ):
            first = module.collect(target, "task-triage")
            second = module.collect(target, "task-review")
        self.assertEqual(first["artifact_root"], second["artifact_root"])
        self.assertFalse(first["retrieval_complete"])
        self.assertIn("projects/19/issues/7/discussions?per_page=100&page=1", calls)

    def test_mr_requires_exact_refs_and_head_filtered_pipelines(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py", "canonical_gitlab_sha"
        )
        target = {
            "url": "https://gitlab.example/group/project/-/merge_requests/7",
            "hostname": "gitlab.example",
            "project_path": "group/project",
            "kind": "merge_requests",
            "iid": 7,
        }
        calls: list[str] = []

        def fake(_hostname: str, endpoint: str) -> object:
            calls.append(endpoint)
            if endpoint.startswith("projects/group%2Fproject"):
                return {"id": 19}
            if endpoint == "projects/19/merge_requests/7":
                return {
                    "iid": 7,
                    "labels": [],
                    "diff_refs": {"base_sha": "a", "start_sha": "b", "head_sha": "c"},
                }
            if endpoint == "projects/19/merge_requests/7/changes":
                return {
                    "changes": [],
                    "diff_refs": {"base_sha": "a", "start_sha": "b", "head_sha": "c"},
                }
            if endpoint.startswith("projects/19/merge_requests/7/commits"):
                return [{"id": "c"}]
            return []

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {"XDG_STATE_HOME": temporary}),
            patch.object(module, "glab_json", side_effect=fake),
        ):
            bundle = module.collect(target, "code-review")
        self.assertTrue(bundle["retrieval_complete"])
        self.assertIn("projects/19/pipelines?sha=c&per_page=100&page=1", calls)
        self.assertIn("projects/19/merge_requests/7/commits?per_page=100&page=1", calls)

    def test_review_decision_requires_independent_critic_and_all_responses(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py", "canonical_gitlab_critic"
        )
        receipt = {
            "schema": "portable-gitlab/critic-receipt/v2",
            "external_mutations": False,
            "evidence_digest": "evidence",
            "run_id": "critic-run",
            "session_id": "critic-session",
            "findings": [{"id": "critic-1"}],
        }
        report: dict[str, Any] = {
            "schema": "portable-gitlab/review-decision/v2",
            "mode": "deep",
            "external_mutations": False,
            "evidence_digest": "evidence",
            "finalize_digest": "a" * 64,
            "verdict": "not_ready",
            "run_id": "primary-run",
            "session_id": "primary-session",
            "findings": [{"id": "primary-1"}],
            "unresolved_threads": [{"id": "thread-1"}],
            "responses": [
                {"id": "primary-1", "decision": "reject", "reason": "not applicable"},
                {"id": "critic-1", "decision": "accept", "reason": "confirmed"},
                {"id": "thread-1", "decision": "accept", "reason": "needs resolution"},
            ],
        }
        module.validate_critic(receipt, "evidence")
        with self.assertRaises(module.WorkflowError):
            module.validate_critic({**receipt, "evidence_digest": "other"}, "evidence")
        with self.assertRaises(module.WorkflowError):
            module.validate_critic(
                {key: value for key, value in receipt.items() if key != "external_mutations"},
                "evidence",
            )
        module.validate_decision(report, "evidence", receipt, "deep")
        report["responses"].pop()
        with self.assertRaises(module.WorkflowError):
            module.validate_decision(report, "evidence", receipt, "deep")

    def test_review_modes_require_independent_receipts_and_dispositions(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py", "canonical_gitlab_modes"
        )
        report: dict[str, Any] = {
            "schema": "portable-gitlab/review-decision/v2",
            "mode": "fast",
            "external_mutations": False,
            "evidence_digest": "evidence",
            "finalize_digest": "a" * 64,
            "verdict": "not_ready",
            "run_id": "primary-run",
            "session_id": "primary-session",
            "findings": [{"id": "finding"}],
            "unresolved_threads": [{"id": "thread"}],
            "responses": [
                {"id": "finding", "decision": "accept", "reason": "confirmed"},
                {"id": "thread", "decision": "reject", "reason": "deferred"},
            ],
        }
        for mode in ("normal", "deep"):
            with self.subTest(mode=mode):
                with self.assertRaises(module.WorkflowError):
                    module.validate_decision(report, "evidence", None, mode)
        with self.assertRaises(module.WorkflowError):
            module.validate_decision(report, "evidence", None, "fast")
        report["low_risk"] = True
        module.validate_decision(report, "evidence", None, "fast")
        report["verdict"] = "ready"
        report["blocking_findings"] = True
        with self.assertRaises(module.WorkflowError):
            module.validate_decision(report, "evidence", None, "fast")

    def test_runner_final_review_requires_bound_current_finalize_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            for arguments in (
                ("init", "-q"),
                ("config", "user.email", "reviewer@example.invalid"),
                ("config", "user.name", "Example Reviewer"),
            ):
                subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
            source = repository / "review.txt"
            source.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "review.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            base_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            source.write_text("base\nreviewed change\n", encoding="utf-8")
            subprocess.run(["git", "commit", "-qam", "change"], cwd=repository, check=True)
            head_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            _glab, state = self.fake_glab(root)
            log = root / "glab.log"
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(log),
                "FAKE_BASE_SHA": base_sha,
                "FAKE_START_SHA": base_sha,
                "FAKE_HEAD_SHA": head_sha,
                "FAKE_CHANGED_PATH": "review.txt",
                "FAKE_DISCUSSION": "1",
                "FAKE_MR_STATE": "merged",
            }
            target = "https://gitlab.example/group/project/-/merge_requests/7"
            batch = self.run_runner(
                "code-review", "prepare", "--url", target, "--url", target, env=environment
            )
            self.assertEqual(batch.returncode, 2)
            self.assertFalse(log.exists())
            self.assertEqual(
                self.run_runner("code-review", "scaffold-batch", env=environment).returncode, 2
            )
            prepared = self.run_runner("code-review", "prepare", "--url", target, env=environment)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
            self.assertTrue(
                json.loads(prepared.stdout)["items"][0]["complete"], Path(evidence).read_text()
            )
            evidence_digest = hashlib.sha256(Path(evidence).read_bytes()).hexdigest()
            artifact_root = json.loads(prepared.stdout)["items"][0]["artifact_root"]
            context_result = self.run_runner(
                "code-review",
                "context",
                "--evidence",
                evidence,
                "--repo-root",
                str(repository),
                env=environment,
            )
            self.assertEqual(context_result.returncode, 0, context_result.stderr)
            context = json.loads(context_result.stdout)
            self.assertEqual(context["role"], "reviewer")
            self.assertEqual(context["counts"]["open_resolvable"], 1)
            context_digest = context["digest"]
            context_path = context["artifact_path"]
            finalized = self.run_runner(
                "code-review", "finalize", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(finalized.returncode, 0, finalized.stdout + finalized.stderr)
            finalize_digest = json.loads(finalized.stdout)["digest"]
            finalize_report = json.loads(finalized.stdout)["artifact_path"]
            primary_finding = {
                "id": "primary-1",
                "severity": "high",
                "summary": "Retry can repeat the external operation",
                "risk": "A retry can execute the operation twice.",
                "evidence": [f"{target}#note_42 at {head_sha}"],
                "consequence": "Users can observe duplicate side effects.",
                "relation_to_change": "The reviewed change adds the retry path.",
                "minimum_fix": "Persist an idempotency key before the external call.",
            }
            critic_finding = {
                "id": "critic-1",
                "severity": "medium",
                "summary": "Retry failure is not observable",
                "risk": "Operators cannot distinguish retry exhaustion.",
                "evidence": [f"The exact reviewed SHA is {head_sha}."],
                "consequence": "Incident diagnosis takes longer.",
                "relation_to_change": "The new retry path emits no terminal signal.",
                "minimum_fix": "Emit the existing terminal retry metric.",
            }
            receipt = root / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/critic-receipt/v2",
                        "external_mutations": False,
                        "evidence_digest": evidence_digest,
                        "run_id": "critic-run",
                        "session_id": "critic-session",
                        "findings": [critic_finding],
                    }
                ),
                encoding="utf-8",
            )
            decision = root / "decision.json"
            decision.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/review-decision/v2",
                        "mode": "deep",
                        "external_mutations": False,
                        "evidence_digest": evidence_digest,
                        "finalize_digest": finalize_digest,
                        "context_digest": context_digest,
                        "verdict": "not_ready",
                        "run_id": "primary-run",
                        "session_id": "primary-session",
                        "findings": [primary_finding],
                        "unresolved_threads": [{"id": "42"}],
                        "responses": [
                            {"id": "primary-1", "decision": "accept", "reason": "confirmed"},
                            {"id": "critic-1", "decision": "accept", "reason": "confirmed"},
                            {"id": "42", "decision": "accept", "reason": "still open"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            reviewed = self.run_runner(
                "code-review",
                "finalize-review",
                "--evidence",
                evidence,
                "--report",
                str(decision),
                "--context",
                context_path,
                "--critic-receipt",
                str(receipt),
                "--finalize-report",
                finalize_report,
                "--mode",
                "deep",
                env=environment,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            reviewed_result = json.loads(reviewed.stdout)
            self.assertFalse(reviewed_result["external_mutations"])
            review_content = root / "review-content.json"
            review_content.write_text(
                json.dumps(
                    {
                        "summary": "The change is small and preserves the reviewed contract.",
                        "architecture_assessment": "The responsibility remains with its existing owner.",
                        "semver_impact": "patch",
                        "semver_rationale": "The fix changes behavior without changing the public API.",
                        "mr_metadata_assessment": {
                            "title": {
                                "status": "needs_change",
                                "rationale": "The title does not identify the affected behavior.",
                                "recommendation": "Name the affected retry behavior.",
                            },
                            "description": {
                                "status": "ok",
                                "rationale": "The description states the intended behavior.",
                                "recommendation": None,
                            },
                            "labels": {
                                "status": "needs_change",
                                "rationale": "The MR has no labels.",
                                "recommendation": "Apply the project-required labels.",
                            },
                            "workflow_state": {
                                "status": "ok",
                                "rationale": "The MR is already merged and remains commentable.",
                                "recommendation": None,
                            },
                            "overall": {
                                "status": "needs_change",
                                "rationale": "Title and labels need clearer release metadata.",
                                "recommendation": "Correct metadata independently of code findings.",
                            },
                        },
                        "checks": ["Compared the exact base and head revisions."],
                        "findings": [primary_finding],
                        "thread_decisions": [
                            {
                                "id": "42",
                                "url": f"{target}#note_42",
                                "state": "open",
                                "assessment": "accepted",
                                "rationale": "The issue remains present at the exact head SHA.",
                                "outcome": "no_publication",
                                "proposed_response": "The retry needs an idempotency key before the call.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            review_plan = self.run_runner(
                "code-review",
                "scaffold-review",
                "--evidence",
                evidence,
                "--context",
                context_path,
                "--decision",
                reviewed_result["artifact_path"],
                "--content",
                str(review_content),
                env=environment,
            )
            self.assertEqual(review_plan.returncode, 0, review_plan.stderr)
            plan_result = json.loads(review_plan.stdout)
            self.assertTrue(Path(plan_result["markdown_path"]).is_file())
            markdown = Path(plan_result["markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("Retry can repeat the external operation", markdown)
            self.assertIn(f"{target}#note_42", markdown)
            self.assertIn("MR metadata assessment", markdown)
            self.assertIn("The fix changes behavior without changing the public API.", markdown)
            self.assertIn("MR state: `merged`", markdown)
            self.assertEqual(len(plan_result["publication_body_paths"]), 1)
            body_path = Path(plan_result["publication_body_paths"][0])
            self.assertTrue(body_path.is_absolute())
            self.assertTrue(body_path.is_file())
            self.assertIn("--method POST", plan_result["publication_commands"][0])
            self.assertIn(f"body=@{body_path}", plan_result["publication_commands"][0])
            self.assertIn("--method GET", plan_result["publication_commands"][0])
            self.assertIn("sha256sum --check --status", plan_result["publication_commands"][0])
            environment["FAKE_CURRENT_USER"] = "author"
            stale_plan = self.run_runner(
                "code-review",
                "scaffold-review",
                "--evidence",
                evidence,
                "--context",
                context_path,
                "--decision",
                reviewed_result["artifact_path"],
                "--content",
                str(review_content),
                env=environment,
            )
            self.assertEqual(stale_plan.returncode, 2)
            author_context = self.run_runner(
                "code-review",
                "context",
                "--evidence",
                evidence,
                "--repo-root",
                str(repository),
                env=environment,
            )
            self.assertEqual(author_context.returncode, 0, author_context.stderr)
            self.assertEqual(json.loads(author_context.stdout)["role"], "author")
            environment.pop("FAKE_CURRENT_USER")
            duplicate = json.loads(receipt.read_text(encoding="utf-8"))
            duplicate["run_id"] = "primary-run"
            receipt.write_text(json.dumps(duplicate), encoding="utf-8")
            self.assertEqual(
                self.run_runner(
                    "code-review",
                    "finalize-review",
                    "--evidence",
                    evidence,
                    "--report",
                    str(decision),
                    "--context",
                    context_path,
                    "--critic-receipt",
                    str(receipt),
                    "--finalize-report",
                    finalize_report,
                    "--mode",
                    "deep",
                    env=environment,
                ).returncode,
                2,
            )
            receipt.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/critic-receipt/v2",
                        "external_mutations": False,
                        "evidence_digest": evidence_digest,
                        "run_id": "critic-run",
                        "session_id": "critic-session",
                        "findings": [critic_finding],
                    }
                ),
                encoding="utf-8",
            )
            state.write_text("changed", encoding="utf-8")
            newer = self.run_runner("code-review", "prepare", "--url", target, env=environment)
            self.assertEqual(newer.returncode, 0, newer.stderr)
            stale = self.run_runner(
                "code-review",
                "finalize-review",
                "--evidence",
                evidence,
                "--report",
                str(decision),
                "--context",
                context_path,
                "--critic-receipt",
                str(receipt),
                "--finalize-report",
                finalize_report,
                "--mode",
                "deep",
                env=environment,
            )
            self.assertEqual(stale.returncode, 2)
            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(calls)
            self.assertTrue(all("GET" in call and "api" in call for call in calls))

    def test_release_ready_requires_all_bound_gates_and_fresh_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _glab, state = self.fake_glab(root)
            log = root / "glab.log"
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(log),
            }
            prepared = self.run_runner(
                "release-review",
                "prepare",
                "--url",
                "https://gitlab.example/group/project/-/merge_requests/7",
                env=environment,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            item = json.loads(prepared.stdout)["items"][0]
            evidence = Path(str(item["artifact_path"]))
            evidence_digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
            identity = {"base_sha": "a", "start_sha": "b", "head_sha": "c"}
            readiness = root / "readiness.json"
            readiness.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/release-readiness/v2",
                        "external_mutations": False,
                        "evidence_digest": evidence_digest,
                        "verdict": "ready",
                        "readiness": True,
                        "gates": {
                            name: {"status": "passed", "evidence": [name], "range": identity}
                            for name in ("semver", "compatibility", "migration", "rollback", "ci")
                        },
                    }
                ),
                encoding="utf-8",
            )
            recorded = self.run_runner(
                "release-review",
                "record-artifact",
                "--kind",
                "release_readiness",
                "--evidence",
                str(evidence),
                "--input",
                str(readiness),
                env=environment,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            result = self.run_runner(
                "release-review",
                "finalize",
                "--artifact-root",
                str(item["artifact_root"]),
                "--report",
                json.loads(recorded.stdout)["artifact_path"],
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            state.write_text("changed", encoding="utf-8")
            stale = self.run_runner(
                "release-review",
                "finalize",
                "--artifact-root",
                str(item["artifact_root"]),
                "--report",
                json.loads(recorded.stdout)["artifact_path"],
                env=environment,
            )
            self.assertEqual(stale.returncode, 2)
            blocked = json.loads(readiness.read_text(encoding="utf-8"))
            blocked["gates"]["ci"]["status"] = "not_applicable"
            module = load_module(
                ROOT / "shared/references/portable_gitlab/contract.py", "canonical_release_gates"
            )
            with self.assertRaises(module.WorkflowError):
                module.validate_release_readiness(
                    blocked,
                    {
                        "base_sha": "a",
                        "start_sha": "b",
                        "head_sha": "c",
                        "retrieval_complete": True,
                    },
                    evidence_digest,
                )

    @unittest.skip("GitLab task adapter removed in stage 17")
    def test_runner_scaffold_record_rejections_and_v1_finalize_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _glab, _state = self.fake_glab(root)
            log = root / "glab.log"
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(root / "fake-glab-state"),
                "FAKE_GLAB_LOG": str(log),
            }
            target = "https://gitlab.example/group/project/-/merge_requests/7"
            prepared = self.run_runner("code-review", "prepare", "--url", target, env=environment)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            item = json.loads(prepared.stdout)["items"][0]
            content = root / "content.json"
            content.write_text('{"title":"Title","description":"Body"}', encoding="utf-8")
            for command in ("scaffold", "scaffold-batch"):
                with self.subTest(command=command):
                    result = self.run_runner(
                        "code-review",
                        command,
                        "--bundle",
                        str(item["artifact_path"]),
                        "--content",
                        str(content),
                        env=environment,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(json.loads(result.stdout)["external_mutations"])
            analysis = root / "analysis.json"
            evidence_digest = hashlib.sha256(
                Path(str(item["artifact_path"])).read_bytes()
            ).hexdigest()
            analysis.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/analysis-report/v2",
                        "external_mutations": False,
                        "evidence_digest": evidence_digest,
                        "run_id": "analysis-run",
                        "session_id": "analysis-session",
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            recorded = self.run_runner(
                "code-review",
                "record-artifact",
                "--kind",
                "analysis_report",
                "--evidence",
                str(item["artifact_path"]),
                "--input",
                str(analysis),
                env=environment,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            self.assertEqual(
                self.run_runner(
                    "code-review",
                    "record-artifact",
                    "--kind",
                    "review_decision",
                    "--evidence",
                    str(item["artifact_path"]),
                    "--input",
                    str(analysis),
                    env=environment,
                ).returncode,
                2,
            )
            self.assertEqual(
                self.run_runner(
                    "task-triage", "prepare", "--url", target, env=environment
                ).returncode,
                2,
            )
            self.assertEqual(
                self.run_runner(
                    "code-review",
                    "prepare",
                    "--project-url",
                    "https://gitlab.example/group/project",
                    env=environment,
                ).returncode,
                2,
            )
            legacy = Path(str(item["artifact_root"])) / "bundle.json"
            legacy.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile": "code-review",
                        "target": {
                            "url": target,
                            "hostname": "gitlab.example",
                            "project_path": "group/project",
                            "project_id": 19,
                            "kind": "merge_requests",
                            "iid": 7,
                        },
                        "retrieval_complete": False,
                    }
                ),
                encoding="utf-8",
            )
            (Path(str(item["artifact_root"])) / "current.json").unlink()
            legacy_final = self.run_runner(
                "code-review",
                "finalize",
                "--artifact-root",
                str(item["artifact_root"]),
                env=environment,
            )
            self.assertEqual(legacy_final.returncode, 2)
            self.assertEqual(json.loads(legacy.read_text(encoding="utf-8"))["schema_version"], 1)


class MattermostAndTeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from scripts import build_skills

        assert build_skills.build(BUILT_SKILLS, False) == 0

    def mattermost_module(self, name: str) -> ModuleType:
        return load_module(
            BUILT_SKILLS / "mattermost/scripts/mattermost.py", f"portable_mattermost_{name}"
        )

    def run_script(
        self,
        skill: str,
        runner: str,
        *arguments: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(BUILT_SKILLS / skill / "scripts" / runner),
                *arguments,
            ],
            cwd=cwd or Path(tempfile.gettempdir()),
            env={**os.environ, "PYTHONPATH": "/invalid", **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )

    def example_team_profile(self, skill: str, name: str) -> dict[str, Any]:
        profile = json.loads(
            (BUILT_SKILLS / skill / "references/team-context.example.json").read_text(
                encoding="utf-8"
            )
        )
        profile["profile"] = name
        return cast("dict[str, Any]", profile)

    def save_team_profile(
        self,
        skill: str,
        candidate: Path,
        name: str,
        environment: dict[str, str],
        *,
        set_default: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        default_flag = ("--set-default",) if set_default else ()
        prepared = self.run_script(
            skill,
            "team_workflow.py",
            "profile-prepare",
            "--name",
            name,
            "--input",
            str(candidate),
            *default_flag,
            cwd=candidate.parent,
            env=environment,
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        preview = json.loads(prepared.stdout)
        return self.run_script(
            skill,
            "team_workflow.py",
            "profile-save",
            "--name",
            name,
            "--input",
            str(candidate),
            "--digest",
            preview["digest"],
            *default_flag,
            cwd=candidate.parent,
            env=environment,
        )

    def test_mattermost_origin_binding_and_missing_auth_do_not_leak_secret(self) -> None:
        module = self.mattermost_module("origin")
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": temporary}):
                first = module.origin_token_file("https://chat.example/team/channels/main")
                second = module.origin_token_file("https://other.example/team/channels/main")
                self.assertNotEqual(first, second)
                module.save_token("https://chat.example", "private-value")
                self.assertEqual(stat_mode(first), 0o600)
        result = self.run_script(
            "mattermost", "mattermost.py", "read", "https://chat.example/team/channels/main"
        )
        self.assertEqual(result.returncode, 3)
        self.assertNotIn("private-value", result.stdout + result.stderr)

        invalid = self.run_script(
            "mattermost", "mattermost.py", "read", "http://chat.example/team/pl/post-1"
        )
        self.assertEqual(invalid.returncode, 2)
        payload = json.loads(invalid.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertFalse(payload["complete"])
        self.assertFalse(payload["external_mutations"])
        self.assertEqual(payload["errors"][0]["code"], "invalid_input")

    def test_mattermost_normalizes_explicit_url_forms_and_rejects_near_misses(self) -> None:
        module = self.mattermost_module("urls")
        expected = {
            "origin": "https://chat.example",
            "kind": "post",
            "route": "pl",
            "team": "team",
            "channel": None,
            "post_id": "post-1",
        }
        self.assertEqual(module.classify_url("https://chat.example/team/pl/post-1"), expected)
        self.assertEqual(
            module.classify_url("https://chat.example/team/channels/general?post=post-1")[
                "post_id"
            ],
            "post-1",
        )
        self.assertEqual(
            module.classify_url("https://chat.example/team/messages/direct-chat")["kind"], "chat"
        )
        self.assertEqual(
            module.classify_url("https://chat.example/team/group/group-chat")["kind"], "chat"
        )
        for value in (
            "http://chat.example/team/pl/post-1",
            "https://chat.example/team/pl/post-1/extra",
            "https://chat.example/team/channels/general?post=one&post=two",
            "https://chat.example/team/unknown/general",
            "https://user@chat.example/team/pl/post-1",
        ):
            with self.subTest(value=value):
                with self.assertRaises(module.MattermostError):
                    module.classify_url(value)

    def test_mattermost_pagination_deduplicates_and_marks_repeated_pages_partial(self) -> None:
        module = self.mattermost_module("pages")
        posts = {
            str(index): {"id": str(index), "channel_id": "channel-id", "create_at": index}
            for index in range(1, 201)
        }
        page = {"order": list(posts), "posts": posts}

        class FakeClient:
            def get(self, path: str) -> object:
                return page

        result, complete, pages, errors, warnings = module.read_channel(
            FakeClient(),
            {"id": "channel-id"},
            0,
            1000,
        )
        self.assertFalse(complete)
        self.assertEqual(len(result), 200)
        self.assertEqual(pages, 2)
        self.assertEqual(errors[0]["code"], "repeated_page")
        self.assertEqual(warnings, [])

    def test_mattermost_pagination_collects_pages_and_marks_error_or_limit_partial(self) -> None:
        module = self.mattermost_module("pagination_bounds")
        first = {
            str(index): {
                "id": str(index),
                "channel_id": "channel-id",
                "create_at": index,
            }
            for index in range(1, 201)
        }
        second = {"last": {"id": "last", "channel_id": "channel-id", "create_at": 201}}
        first_page = {"order": list(first), "posts": first}
        second_page = {"order": ["last"], "posts": second}

        class CompleteClient:
            def get(self, path: str) -> object:
                if path.endswith("/reactions"):
                    return []
                responses = {
                    "/users/me": {"id": "viewer"},
                    "/teams/name/team": {"id": "team-id"},
                    "/teams/team-id/channels/name/channel": {"id": "channel-id", "name": "channel"},
                }
                if path.startswith("/channels/channel-id/posts?"):
                    return second_page if "before=" in path else first_page
                return responses[path]

        posts, complete, pages, errors, warnings = module.read_channel(
            CompleteClient(), {"id": "channel-id"}, 0, 1000
        )
        self.assertTrue(complete)
        self.assertEqual(len(posts), 201)
        self.assertEqual(pages, 2)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

        class ErrorClient:
            def get(self, path: str) -> object:
                if path == "/users/me":
                    return {"id": "viewer"}
                if path == "/teams/name/team":
                    return {"id": "team-id"}
                if path == "/teams/team-id/channels/name/channel":
                    return {"id": "channel-id", "name": "channel"}
                if path.startswith("/channels/channel-id/posts?") and "before=" not in path:
                    return first_page
                raise module.MattermostError("page failed")

        posts, complete, pages, errors, _ = module.read_channel(
            ErrorClient(), {"id": "channel-id"}, 0, 1000
        )
        self.assertFalse(complete)
        self.assertEqual(len(posts), 200)
        self.assertEqual(pages, 1)
        self.assertEqual(errors[0]["code"], "page_unavailable")

        with patch.object(module, "MAX_PAGES", 1):
            posts, complete, pages, errors, _ = module.read_channel(
                CompleteClient(), {"id": "channel-id"}, 0, 1000
            )
        self.assertFalse(complete)
        self.assertEqual(len(posts), 200)
        self.assertEqual(pages, 1)
        self.assertEqual(errors[0]["code"], "pagination_limit")

        def read_exit(client: object, *, max_pages: int | None = None) -> dict[str, object]:
            output = io.StringIO()
            pages_patch = (
                patch.object(module, "MAX_PAGES", max_pages)
                if max_pages is not None
                else nullcontext()
            )
            with pages_patch:
                with patch.object(module, "read_token", return_value="private-value"):
                    with patch.object(module, "Client", return_value=client):
                        with redirect_stdout(output):
                            self.assertEqual(
                                module.main(
                                    [
                                        "read",
                                        "https://chat.example/team/channels/channel",
                                        "--since",
                                        "1970-01-01T00:00:00+00:00",
                                        "--no-cache",
                                    ]
                                ),
                                1,
                            )
            observed = json.loads(output.getvalue())
            self.assertIsInstance(observed, dict)
            return cast(dict[str, object], observed)

        for client, max_pages, error_code in (
            (ErrorClient(), None, "page_unavailable"),
            (CompleteClient(), 1, "pagination_limit"),
        ):
            with self.subTest(error_code=error_code):
                observed = read_exit(client, max_pages=max_pages)
                self.assertEqual(observed["status"], "partial")
                errors = cast(list[dict[str, object]], observed["errors"])
                self.assertIsInstance(errors, list)
                self.assertIsInstance(errors[0], dict)
                self.assertEqual(errors[0]["code"], error_code)

    def test_mattermost_partial_thread_and_members_preserve_safe_evidence(self) -> None:
        module = self.mattermost_module("partial")
        post = {"id": "reply", "root_id": "root", "channel_id": "channel-id", "create_at": 1}

        class ThreadClient:
            def get(self, path: str) -> object:
                raise module.MattermostError("thread unavailable")

        posts, complete, errors, warnings, cache_hit, cache_age = module.read_post(
            ThreadClient(),
            post,
            None,
            read_cache=False,
            write_cache=False,
            current_ms=1000,
        )
        self.assertFalse(complete)
        self.assertEqual(posts, [post])
        self.assertEqual(errors[0]["code"], "thread_unavailable")
        self.assertEqual(warnings[0]["code"], "thread_unavailable")
        self.assertFalse(cache_hit)
        self.assertIsNone(cache_age)
        summary = module.result_base(scope="post")
        summary.update({"posts": posts, "complete": False, "errors": errors})
        self.assertEqual(module.finalize_result(summary)["counts"]["posts"], 1)

        calls: list[str] = []

        class MembersClient:
            def get(self, path: str) -> Any:
                calls.append(path)
                responses = {
                    "/users/me": {"id": "viewer"},
                    "/teams/name/team": {"id": "team-id"},
                    "/teams/team-id/channels/name/channel": {"id": "channel-id", "name": "channel"},
                    "/channels/channel-id/members?page=0&per_page=200": [
                        {"user_id": "one"},
                        {"user_id": "two"},
                    ],
                    "/users/one": {"username": "alice"},
                }
                if path == "/users/two":
                    raise module.MattermostError("profile forbidden")
                return responses[path]

        with patch.object(module, "read_token", return_value="private-value"):
            with patch.object(module, "Client", return_value=MembersClient()):
                result = module.collect_members("https://chat.example/team/channels/channel")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["members"][0]["username"], "alice")
        self.assertEqual(result["unresolved_ids"], ["two"])
        self.assertTrue(
            all(
                "channel-id" in path or path.startswith("/teams/") or path.startswith("/users/")
                for path in calls
            )
        )

    def test_mattermost_cache_is_identity_bound_expiring_and_revalidated(self) -> None:
        module = self.mattermost_module("cache")
        root = {
            "id": "post-1",
            "channel_id": "channel-id",
            "root_id": "",
            "create_at": 1,
            "update_at": 1,
        }
        with tempfile.TemporaryDirectory() as temporary:
            environment = {"XDG_CACHE_HOME": temporary}
            with patch.dict(os.environ, environment, clear=False):
                fetched_at = module.now() * 1000
                with module.CacheStore("https://chat.example", "user-one") as store:
                    store.put_thread("post-1", [root], fetched_at, complete=True)
                    self.assertIsNotNone(store.get_post("post-1"))
                with module.CacheStore("https://chat.example", "user-two") as store:
                    self.assertIsNone(store.get_post("post-1"))

        calls: list[str] = []

        class CachedClient:
            def get(self, path: str) -> Any:
                calls.append(path)
                if path == "/users/me":
                    return {"id": "viewer"}
                if path == "/posts/post-1":
                    return root
                raise AssertionError(path)

        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"XDG_CACHE_HOME": temporary}, clear=False):
                with module.CacheStore("https://chat.example", "viewer") as store:
                    store.put_thread(
                        "post-1",
                        [root],
                        module.now() * 1000,
                        complete=True,
                    )
                with patch.object(module, "read_token", return_value="private-value"):
                    with patch.object(module, "Client", return_value=CachedClient()):
                        cached = module.read_one(
                            "https://chat.example/team/pl/post-1",
                            None,
                            None,
                            True,
                            True,
                            include_reactions=False,
                        )
        self.assertTrue(cached["cache_hit"])
        self.assertTrue(cached["access_revalidated"])
        self.assertEqual(calls, ["/users/me", "/posts/post-1"])

    def test_mattermost_cache_flags_and_result_exit_contract(self) -> None:
        module = self.mattermost_module("flags")
        complete = module.result_base(scope="post")
        complete.update(
            {
                "status": "partial",
                "complete": False,
                "posts": [{"id": "post-1", "create_at": 1}],
                "errors": [module.error_item("thread_unavailable", "unavailable")],
            }
        )
        for flag, expected in (("--refresh", (False, True)), ("--no-cache", (False, False))):
            with self.subTest(flag=flag):
                output = io.StringIO()
                with patch.object(module, "read_one", return_value=complete) as read_one:
                    with redirect_stdout(output):
                        code = module.main(["read", "https://chat.example/team/pl/post-1", flag])
                self.assertEqual(code, 1)
                self.assertEqual(read_one.call_args.args[-2:], expected)
                observed = json.loads(output.getvalue())
                self.assertEqual(observed["status"], "partial")
                self.assertFalse(observed["complete"])
                self.assertFalse(observed["external_mutations"])
                self.assertIn("pages", observed)
                self.assertIn("unresolved_ids", observed)

    def test_mattermost_client_uses_only_get_requests(self) -> None:
        module = self.mattermost_module("get_only")
        seen: list[Request] = []
        case = self

        class Response:
            def read(self, _: int) -> bytes:
                return b'{"id":"viewer"}'

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *arguments: object) -> None:
                return None

        class Opener:
            def open(self, request: Request, *, timeout: int) -> Response:
                seen.append(request)
                case.assertEqual(timeout, 30)
                return Response()

        with patch.object(module.urllib.request, "build_opener", return_value=Opener()):
            self.assertEqual(
                module.Client("https://chat.example", "private-value").get("/users/me"),
                {"id": "viewer"},
            )
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].get_method(), "GET")
        self.assertEqual(seen[0].full_url, "https://chat.example/api/v4/users/me")
        self.assertIsNone(module.NoRedirect().redirect_request())

    def test_mattermost_auth_and_cache_confirmation_are_one_use_and_redact_secret(self) -> None:
        module = self.mattermost_module("confirm")
        secret = "private-value"
        with tempfile.TemporaryDirectory() as temporary:
            environment = {
                "XDG_CONFIG_HOME": str(Path(temporary) / "config"),
                "XDG_CACHE_HOME": str(Path(temporary) / "cache"),
            }
            with patch.dict(os.environ, environment, clear=False):
                preview = module.prepare_receipt("auth", origin="https://chat.example")
                digest = preview["digest"]
                with patch.object(
                    sys,
                    "stdin",
                    io.StringIO(
                        json.dumps(
                            [{"name": "MMAUTHTOKEN", "domain": "chat.example", "value": secret}]
                        )
                    ),
                ):
                    self.assertEqual(
                        module.main(["auth", "apply", "https://chat.example", "--confirm", digest]),
                        0,
                    )
                with patch.object(
                    sys,
                    "stdin",
                    io.StringIO(
                        json.dumps(
                            [{"name": "MMAUTHTOKEN", "domain": "chat.example", "value": secret}]
                        )
                    ),
                ):
                    self.assertEqual(
                        module.main(["auth", "apply", "https://chat.example", "--confirm", digest]),
                        2,
                    )
                before = module.origin_token_file("https://chat.example").read_text(
                    encoding="utf-8"
                )
                tampered = module.prepare_receipt("auth", origin="https://chat.example")
                receipt = module.receipt_path(tampered["digest"])
                payload = json.loads(receipt.read_text(encoding="utf-8"))
                payload["expires_at"] = "invalid"
                receipt.write_text(json.dumps(payload), encoding="utf-8")
                with patch.object(
                    sys,
                    "stdin",
                    io.StringIO(
                        json.dumps(
                            [
                                {
                                    "name": "MMAUTHTOKEN",
                                    "domain": "chat.example",
                                    "value": "other-value",
                                }
                            ]
                        )
                    ),
                ):
                    self.assertEqual(
                        module.main(
                            [
                                "auth",
                                "apply",
                                "https://chat.example",
                                "--confirm",
                                tampered["digest"],
                            ]
                        ),
                        2,
                    )
                self.assertEqual(
                    module.origin_token_file("https://chat.example").read_text(encoding="utf-8"),
                    before,
                )
                cache_preview = module.prepare_receipt("cache-clear", path=module.cache_path())
                self.assertEqual(
                    module.main(["cache", "clear", "--confirm", cache_preview["digest"]]), 0
                )
                self.assertEqual(
                    module.main(["cache", "clear", "--confirm", cache_preview["digest"]]), 2
                )
                receipt_text = "".join(
                    path.read_text(encoding="utf-8")
                    for path in module.receipt_root().glob("*.json")
                )
                self.assertNotIn(secret, receipt_text)

    def test_mattermost_members_stays_within_one_channel(self) -> None:
        module = self.mattermost_module("members")
        calls: list[str] = []

        class FakeClient:
            def get(self, path: str) -> Any:
                calls.append(path)
                responses = {
                    "/users/me": {"id": "viewer"},
                    "/teams/name/team": {"id": "team-id"},
                    "/teams/team-id/channels/name/channel": {"id": "channel-id", "name": "channel"},
                    "/channels/channel-id/members?page=0&per_page=200": [{"user_id": "one"}],
                    "/users/one": {"username": "alice"},
                }
                return responses[path]

        with patch.object(module, "read_token", return_value="token"):
            with patch.object(module, "Client", return_value=FakeClient()):
                result = module.collect_members("https://chat.example/team/channels/channel")
        self.assertTrue(result["complete"])
        self.assertEqual(result["members"][0]["username"], "alice")
        self.assertTrue(
            all(
                "channel-id" in path
                or path.startswith("/teams/")
                or path.startswith("/users/one")
                or path == "/users/me"
                for path in calls
            )
        )

    def test_mattermost_safe_post_keeps_reactions_and_drops_attachments(self) -> None:
        module = self.mattermost_module("safe-post")
        post = {
            "id": "post",
            "message": "untrusted",
            "attachments": [{"path": "/secret/file"}],
            "reactions": [{"emoji_name": "+1", "user_id": "viewer"}],
        }
        self.assertEqual(
            module.safe_post(post),
            {
                "id": "post",
                "message": "untrusted",
                "reactions": [{"emoji": "+1", "user": "viewer"}],
            },
        )

    def test_team_digest_rejects_stale_tampered_and_expired_plans_then_reports_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "artifact.txt"
            source.write_text("first", encoding="utf-8")
            environment = {"XDG_STATE_HOME": str(root / "state")}
            preview = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-prepare",
                "--target",
                "out.txt",
                "--input",
                str(source),
                cwd=root,
                env=environment,
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            prepared = json.loads(preview.stdout)
            digest = prepared["digest"]
            self.assertEqual(prepared["status"], "prepared")
            self.assertIn(digest, prepared["apply_command"])
            self.assertTrue(Path(prepared["artifact_path"]).is_file())
            source.write_text("second", encoding="utf-8")
            stale = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-apply",
                "--target",
                "out.txt",
                "--input",
                str(source),
                "--digest",
                digest,
                cwd=root,
                env=environment,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("digest", json.loads(stale.stdout)["error"]["message"])
            fresh = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-prepare",
                "--target",
                "out.txt",
                "--input",
                str(source),
                cwd=root,
                env=environment,
            )
            fresh_digest = json.loads(fresh.stdout)["digest"]
            plan = Path(json.loads(fresh.stdout)["artifact_path"])
            tampered = json.loads(plan.read_text(encoding="utf-8"))
            tampered["payload"]["target"] = "other.txt"
            plan.write_text(json.dumps(tampered), encoding="utf-8")
            tampered_apply = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-apply",
                "--target",
                "out.txt",
                "--input",
                str(source),
                "--digest",
                fresh_digest,
                cwd=root,
                env=environment,
            )
            self.assertNotEqual(tampered_apply.returncode, 0)
            expired = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-prepare",
                "--target",
                "expired.txt",
                "--input",
                str(source),
                cwd=root,
                env=environment,
            )
            expired_payload = json.loads(expired.stdout)
            expired_plan = Path(expired_payload["artifact_path"])
            expired_document = json.loads(expired_plan.read_text(encoding="utf-8"))
            expired_document["expires_at"] = 0
            expired_plan.write_text(json.dumps(expired_document), encoding="utf-8")
            expired_apply = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-apply",
                "--target",
                "expired.txt",
                "--input",
                str(source),
                "--digest",
                expired_payload["digest"],
                cwd=root,
                env=environment,
            )
            self.assertNotEqual(expired_apply.returncode, 0)
            valid = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-prepare",
                "--target",
                "valid.txt",
                "--input",
                str(source),
                cwd=root,
                env=environment,
            )
            valid_digest = json.loads(valid.stdout)["digest"]
            applied = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-apply",
                "--target",
                "valid.txt",
                "--input",
                str(source),
                "--digest",
                valid_digest,
                cwd=root,
                env=environment,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            applied_payload = json.loads(applied.stdout)
            self.assertEqual(applied_payload["status"], "applied")
            self.assertTrue(Path(applied_payload["report_path"]).is_file())
            self.assertEqual(
                self.run_script(
                    "team-sprint-start",
                    "team_workflow.py",
                    "artifact-apply",
                    "--target",
                    "valid.txt",
                    "--input",
                    str(source),
                    "--digest",
                    valid_digest,
                    cwd=root,
                    env=environment,
                ).returncode,
                2,
            )
            escaped = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-prepare",
                "--target",
                "../outside.txt",
                "--input",
                str(source),
                cwd=root,
                env=environment,
            )
            self.assertNotEqual(escaped.returncode, 0)
            self.assertFalse((root.parent / "outside.txt").exists())
            linked = root / "linked.txt"
            linked.symlink_to(root.parent / "outside.txt")
            symlink = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-prepare",
                "--target",
                "linked.txt",
                "--input",
                str(source),
                cwd=root,
                env=environment,
            )
            self.assertNotEqual(symlink.returncode, 0)

    def test_team_context_inspect_reports_missing_without_writing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = root / "context.json"
            context.write_text('{"goals": ["goal"]}', encoding="utf-8")
            state = root / "state"
            result = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "context-inspect",
                "--input",
                str(context),
                cwd=root,
                env={"XDG_STATE_HOME": str(state)},
            )
            self.assertEqual(result.returncode, 3, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "setup-required")
            self.assertIn("scope", payload["missing"])
            self.assertFalse(state.exists())

    def test_team_missing_default_profile_is_read_only_setup_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config"
            state = root / "state"
            result = self.run_script(
                "team-retro",
                "team_workflow.py",
                "action-check",
                cwd=root,
                env={"XDG_CONFIG_HOME": str(config), "XDG_STATE_HOME": str(state)},
            )
            self.assertEqual(result.returncode, 3, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "setup-required")
            self.assertEqual(payload["missing"], ["profile.default"])
            self.assertFalse(config.exists())
            self.assertFalse(state.exists())

    def test_team_profile_setup_resolves_default_privately_without_plan_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            profile = self.example_team_profile("team-retro", "platform-team")
            private_marker = "PRIVATE-PROFILE-MARKER"
            profile["team"]["description"] = private_marker
            candidate.write_text(json.dumps(profile), encoding="utf-8")
            environment = {
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_STATE_HOME": str(root / "state"),
            }
            applied = self.save_team_profile("team-retro", candidate, "platform-team", environment)
            self.assertEqual(applied.returncode, 0, applied.stderr)

            profile_root = root / "config/opencode/team-contexts"
            saved = profile_root / "platform-team.json"
            settings = profile_root / "settings.json"
            self.assertEqual(stat_mode(profile_root), 0o700)
            self.assertEqual(stat_mode(saved), 0o600)
            self.assertEqual(stat_mode(settings), 0o600)
            for skill in ("team-retro", "team-roadmap", "slides-prompts-prepare"):
                resolved = self.run_script(
                    skill,
                    "team_workflow.py",
                    "action-check",
                    cwd=root,
                    env=environment,
                )
                self.assertEqual(resolved.returncode, 0, resolved.stderr)
                resolved_payload = json.loads(resolved.stdout)
                self.assertEqual(resolved_payload["context_source"], "profile:platform-team")
                self.assertEqual(resolved_payload["projects"], 1)
                self.assertEqual(Path(resolved_payload["context_path"]), saved)

            retained = "".join(
                path.read_text(encoding="utf-8")
                for path in (root / "state/agent-skills/team-workflow/plans").glob("*.json")
            )
            retained += "".join(
                path.read_text(encoding="utf-8")
                for path in (root / "state/agent-skills/team-workflow/reports").glob("*.json")
            )
            self.assertNotIn(private_marker, retained)

            saved.chmod(0o644)
            insecure = self.run_script(
                "team-retro",
                "team_workflow.py",
                "action-check",
                cwd=root,
                env=environment,
            )
            self.assertEqual(insecure.returncode, 2, insecure.stderr)
            self.assertIn("group or other users", insecure.stderr)

    def test_team_profile_inspect_is_action_specific_and_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            profile = self.example_team_profile("team-retro", "platform-team")
            del profile["actions"]["retro"]
            candidate.write_text(json.dumps(profile), encoding="utf-8")
            missing = self.run_script(
                "team-retro",
                "team_workflow.py",
                "profile-inspect",
                "--input",
                str(candidate),
                cwd=root,
                env={
                    "XDG_CONFIG_HOME": str(root / "config"),
                    "XDG_STATE_HOME": str(root / "state"),
                },
            )
            self.assertEqual(missing.returncode, 3, missing.stderr)
            self.assertIn("actions.retro", json.loads(missing.stdout)["missing"])

            profile["unexpected"] = "value"
            candidate.write_text(json.dumps(profile), encoding="utf-8")
            invalid = self.run_script(
                "team-retro",
                "team_workflow.py",
                "profile-inspect",
                "--input",
                str(candidate),
                cwd=root,
            )
            self.assertEqual(invalid.returncode, 2, invalid.stderr)
            self.assertIn("unexpected", json.loads(invalid.stdout)["invalid"])

            del profile["unexpected"]
            private_value = "SHOULD-NOT-LEAK"
            profile["extensions"] = {"access_token": private_value}
            candidate.write_text(json.dumps(profile), encoding="utf-8")
            unsafe = self.run_script(
                "team-retro",
                "team_workflow.py",
                "profile-inspect",
                "--input",
                str(candidate),
                cwd=root,
            )
            self.assertEqual(unsafe.returncode, 2, unsafe.stderr)
            self.assertNotIn(private_value, unsafe.stdout + unsafe.stderr)

    def test_team_explicit_profile_overrides_default_without_rebinding_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_STATE_HOME": str(root / "state"),
            }
            default_candidate = root / "default.json"
            default_candidate.write_text(
                json.dumps(self.example_team_profile("team-retro", "default-team")),
                encoding="utf-8",
            )
            self.assertEqual(
                self.save_team_profile(
                    "team-retro", default_candidate, "default-team", environment
                ).returncode,
                0,
            )
            other_candidate = root / "other.json"
            other_profile = self.example_team_profile("team-retro", "other-team")
            other_profile["projects"].append(
                {
                    "key": "second-project",
                    "name": "Second Project",
                    "path": "platform/second-project",
                    "category": "Core",
                    "description": "Second bounded project.",
                    "include": True,
                }
            )
            other_candidate.write_text(json.dumps(other_profile), encoding="utf-8")
            self.assertEqual(
                self.save_team_profile(
                    "team-retro",
                    other_candidate,
                    "other-team",
                    environment,
                    set_default=False,
                ).returncode,
                0,
            )
            default = self.run_script(
                "team-retro", "team_workflow.py", "action-check", cwd=root, env=environment
            )
            explicit = self.run_script(
                "team-retro",
                "team_workflow.py",
                "action-check",
                "--profile",
                "other-team",
                cwd=root,
                env=environment,
            )
            self.assertEqual(json.loads(default.stdout)["profile"], "default-team")
            self.assertEqual(json.loads(explicit.stdout)["profile"], "other-team")
            self.assertEqual(json.loads(explicit.stdout)["projects"], 2)

    def test_team_profile_update_rejects_concurrent_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            profile = self.example_team_profile("team-roadmap", "platform-team")
            candidate.write_text(json.dumps(profile), encoding="utf-8")
            environment = {
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_STATE_HOME": str(root / "state"),
            }
            applied = self.save_team_profile(
                "team-roadmap", candidate, "platform-team", environment
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            profile["team"]["members"].append({"id": "bob", "groups": ["platform"], "active": True})
            candidate.write_text(json.dumps(profile), encoding="utf-8")
            prepared = self.run_script(
                "team-roadmap",
                "team_workflow.py",
                "profile-prepare",
                "--name",
                "platform-team",
                "--input",
                str(candidate),
                cwd=root,
                env=environment,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            digest = json.loads(prepared.stdout)["digest"]
            saved = root / "config/opencode/team-contexts/platform-team.json"
            saved.write_text(saved.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            saved.chmod(0o600)
            stale = self.run_script(
                "team-roadmap",
                "team_workflow.py",
                "profile-save",
                "--name",
                "platform-team",
                "--input",
                str(candidate),
                "--digest",
                digest,
                cwd=root,
                env=environment,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("digest", json.loads(stale.stdout)["error"]["message"])

    def test_all_team_skills_use_shared_runtime_and_fixed_action(self) -> None:
        actions = {
            "team-sprint-start": "planning",
            "team-sprint-close": "sprint-close",
            "team-retro": "retro",
            "team-roadmap": "roadmap",
            "slides-prompts-prepare": "slides-prompts",
        }
        source = ROOT / "shared/references/team_runtime/team_workflow.py"
        for skill, action in actions.items():
            with self.subTest(skill=skill):
                self.assertEqual(
                    (BUILT_SKILLS / skill / "scripts/team_workflow.py").read_bytes(),
                    source.read_bytes(),
                )
                result = self.run_script(skill, "team_workflow.py", "--capabilities")
                self.assertEqual(result.returncode, 0, result.stderr)
                context = {
                    "goals": ["goal"],
                    "scope": ["scope"],
                    "cadence": "weekly",
                    "baseline": "baseline",
                    "projects": ["project"],
                    "delivery_signals": ["signal"],
                }
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "context.json"
                    path.write_text(json.dumps(context), encoding="utf-8")
                    checked = self.run_script(
                        skill,
                        "team_workflow.py",
                        "action-check",
                        "--context-file",
                        str(path),
                        cwd=Path(temporary),
                    )
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(json.loads(checked.stdout)["action"], action)

    def test_collaboration_runners_report_invalid_syntax_as_json(self) -> None:
        for skill, runner in (
            ("mattermost", "mattermost.py"),
            ("team-sprint-start", "team_workflow.py"),
        ):
            with self.subTest(skill=skill):
                result = self.run_script(skill, runner, "unknown-command")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "error")


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
