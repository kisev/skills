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
if endpoint.startswith("projects/group%%2Fproject"):
    value = {"id": 19}
elif endpoint == "projects/19/merge_requests/7":
    value = {"iid": 7, "updated_at": "changed" if changed else "fresh", "labels": [], "diff_refs": {"base_sha": "a", "start_sha": "b", "head_sha": "c"}}
elif endpoint == "projects/19/merge_requests/7/changes":
    value = {"changes": [], "diff_refs": {"base_sha": "a", "start_sha": "b", "head_sha": "c"}}
elif endpoint.startswith("projects/19/merge_requests/7/commits"):
    value = [{"id": "c"}]
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
            _glab, state = self.fake_glab(root)
            log = root / "glab.log"
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(log),
            }
            target = "https://gitlab.example/group/project/-/merge_requests/7"
            prepared = self.run_runner("code-review", "prepare", "--url", target, env=environment)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
            self.assertTrue(
                json.loads(prepared.stdout)["items"][0]["complete"], Path(evidence).read_text()
            )
            evidence_digest = hashlib.sha256(Path(evidence).read_bytes()).hexdigest()
            artifact_root = json.loads(prepared.stdout)["items"][0]["artifact_root"]
            finalized = self.run_runner(
                "code-review", "finalize", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(finalized.returncode, 0, finalized.stdout + finalized.stderr)
            finalize_digest = json.loads(finalized.stdout)["digest"]
            finalize_report = json.loads(finalized.stdout)["artifact_path"]
            receipt = root / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/critic-receipt/v2",
                        "external_mutations": False,
                        "evidence_digest": evidence_digest,
                        "run_id": "critic-run",
                        "session_id": "critic-session",
                        "findings": [],
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
                        "verdict": "ready",
                        "run_id": "primary-run",
                        "session_id": "primary-session",
                        "findings": [],
                        "unresolved_threads": [],
                        "responses": [],
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
                "--critic-receipt",
                str(receipt),
                "--finalize-report",
                finalize_report,
                "--mode",
                "deep",
                env=environment,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            self.assertFalse(json.loads(reviewed.stdout)["external_mutations"])
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
                        "findings": [],
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
        posts = {str(index): {"id": str(index), "create_at": index} for index in range(200)}

        class FakeClient:
            def get(self, path: str) -> object:
                if path == "/channels/channel-id/posts?page=0&per_page=200":
                    return {"posts": posts}
                if path == "/channels/channel-id/posts?page=1&per_page=200":
                    return {"posts": posts}
                raise AssertionError(path)

        result, complete, pages, errors, warnings = module.read_channel(
            FakeClient(),
            {"id": "channel-id"},
            {"since": None, "until": None},
        )
        self.assertFalse(complete)
        self.assertEqual(len(result), 200)
        self.assertEqual(pages, 2)
        self.assertEqual(errors[0]["code"], "repeated_page")
        self.assertEqual(warnings, [])

    def test_mattermost_pagination_collects_pages_and_marks_error_or_limit_partial(self) -> None:
        module = self.mattermost_module("pagination_bounds")
        first = {str(index): {"id": str(index), "create_at": index} for index in range(200)}
        second = {"last": {"id": "last", "create_at": 201}}

        class CompleteClient:
            def get(self, path: str) -> object:
                if path.endswith("/reactions"):
                    return []
                responses = {
                    "/users/me": {"id": "viewer"},
                    "/teams/name/team": {"id": "team-id"},
                    "/teams/team-id/channels/name/channel": {"id": "channel-id", "name": "channel"},
                    "/channels/channel-id/posts?page=0&per_page=200": {"posts": first},
                    "/channels/channel-id/posts?page=1&per_page=200": {"posts": second},
                }
                return responses[path]

        posts, complete, pages, errors, warnings = module.read_channel(
            CompleteClient(), {"id": "channel-id"}, {"since": None, "until": None}
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
                if path.endswith("page=0&per_page=200"):
                    return {"posts": first}
                raise module.MattermostError("page failed")

        posts, complete, pages, errors, _ = module.read_channel(
            ErrorClient(), {"id": "channel-id"}, {"since": None, "until": None}
        )
        self.assertFalse(complete)
        self.assertEqual(len(posts), 200)
        self.assertEqual(pages, 1)
        self.assertEqual(errors[0]["code"], "page_unavailable")

        with patch.object(module, "MAX_PAGES", 1):
            posts, complete, pages, errors, _ = module.read_channel(
                CompleteClient(), {"id": "channel-id"}, {"since": None, "until": None}
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
        post = {"id": "reply", "root_id": "root", "create_at": 1}

        class ThreadClient:
            def get(self, path: str) -> object:
                raise module.MattermostError("thread unavailable")

        posts, complete, errors, warnings = module.read_post(ThreadClient(), post)
        self.assertFalse(complete)
        self.assertEqual(posts, [post])
        self.assertEqual(errors[0]["code"], "thread_unavailable")
        self.assertEqual(warnings[0]["code"], "thread_unavailable")
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
        target = module.classify_url("https://chat.example/team/pl/post-1")
        period = None
        result = module.result_base(
            scope="post", target=module.normalized_target(target), period=period
        )
        result.update(
            {"status": "ok", "complete": True, "posts": [{"id": "post-1", "create_at": 1}]}
        )
        with tempfile.TemporaryDirectory() as temporary:
            environment = {"XDG_CACHE_HOME": temporary}
            with patch.dict(os.environ, environment, clear=False):
                key = module.cache_key("https://chat.example", "user-one", target, period)
                module.cache_write(
                    key,
                    origin="https://chat.example",
                    user_id="user-one",
                    target=target,
                    period=period,
                    value=result,
                )
                cached, age = module.cache_read(
                    key,
                    origin="https://chat.example",
                    user_id="user-one",
                    target=target,
                    period=period,
                )
                self.assertEqual(cached["status"], "ok")
                self.assertIsNotNone(age)
                self.assertIsNone(
                    module.cache_read(
                        key,
                        origin="https://chat.example",
                        user_id="user-two",
                        target=target,
                        period=period,
                    )[0]
                )
                with module.cache_connection() as database:
                    database.execute(
                        "UPDATE snapshots_v2 SET fetched = ?",
                        (module.now() - module.CACHE_TTL_SECONDS - 1,),
                    )
                self.assertIsNone(
                    module.cache_read(
                        key,
                        origin="https://chat.example",
                        user_id="user-one",
                        target=target,
                        period=period,
                    )[0]
                )
                with module.cache_connection() as database:
                    database.execute(
                        "CREATE TABLE snapshots (key TEXT PRIMARY KEY, fetched TEXT NOT NULL, payload TEXT NOT NULL)"
                    )
                    database.execute(
                        "INSERT INTO snapshots VALUES (?, ?, ?)",
                        (key, "legacy", json.dumps(result)),
                    )
                self.assertIsNone(
                    module.cache_read(
                        key,
                        origin="https://chat.example",
                        user_id="user-two",
                        target=target,
                        period=period,
                    )[0]
                )

        calls: list[str] = []

        class CachedClient:
            def get(self, path: str) -> Any:
                calls.append(path)
                if path == "/users/me":
                    return {"id": "viewer"}
                if path == "/posts/post-1":
                    return {"id": "post-1", "create_at": 1}
                raise AssertionError(path)

        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"XDG_CACHE_HOME": temporary}, clear=False):
                key = module.cache_key("https://chat.example", "viewer", target, None)
                module.cache_write(
                    key,
                    origin="https://chat.example",
                    user_id="viewer",
                    target=target,
                    period=None,
                    value=result,
                )
                with patch.object(module, "read_token", return_value="private-value"):
                    with patch.object(module, "Client", return_value=CachedClient()):
                        cached = module.read_one(
                            "https://chat.example/team/pl/post-1", None, None, True, True
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
