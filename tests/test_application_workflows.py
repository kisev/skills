from __future__ import annotations

import io
import importlib.util
import hashlib
import json
import os
import shlex
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
    value = {"id": 19, "path_with_namespace": "group/project", "default_branch": "main", "merge_requests_template": os.environ.get("FAKE_MR_DEFAULT_TEMPLATE")}
elif endpoint == "projects/19/repository/commits/main":
    value = {"id": "a"}
elif endpoint == "projects/19/repository/branches/main":
    value = {"name": "main", "commit": {"id": os.environ["FAKE_TARGET_SHA"]}} if "FAKE_TARGET_SHA" in os.environ else []
elif endpoint.startswith("projects/19/releases?"):
    value = json.loads(os.environ.get("FAKE_RELEASES", "[]"))
elif endpoint.startswith("projects/19/repository/tree?"):
    from urllib.parse import parse_qs, urlsplit
    path = parse_qs(urlsplit(endpoint).query).get("path", [""])[0]
    templates = json.loads(os.environ.get("FAKE_MR_TEMPLATES", "[]"))
    if os.environ.get("FAKE_MR_TEMPLATE_FAILURE"):
        sys.exit(1)
    if not templates:
        value = []
    elif path == "":
        value = [{"type": "tree", "path": ".gitlab"}]
    elif path == ".gitlab":
        value = [{"type": "tree", "path": ".gitlab/merge_request_templates"}]
    else:
        value = [{"type": "blob", "path": ".gitlab/merge_request_templates/" + name} for name in templates]
elif endpoint.startswith("projects/19/repository/files/"):
    import base64
    from urllib.parse import unquote
    path = unquote(endpoint.split("/files/", 1)[1].split("?", 1)[0])
    value = {"file_path": path, "encoding": "base64", "content": base64.b64encode(b"## Context\\n\\n## Verification\\n").decode()}
elif endpoint.startswith("projects/19/labels"):
    value = json.loads(os.environ["FAKE_LABEL_CATALOG"]) if "FAKE_LABEL_CATALOG" in os.environ else [{"name": "ship-ready", "description": "semantic-role: change_type; semantic-value: release"}, {"name": "next-compatible", "description": "semantic-role: compatibility; semantic-value: minor"}, {"name": "semver::major", "description": "Breaking compatibility"}, {"name": "semver::patch", "description": "Backward-compatible fix"}]
elif endpoint == "projects/19/merge_requests/7":
    value = {"iid": 7, "title": "Current merge request title", "description": "Current description", "source_branch": "dev", "target_branch": "main", "web_url": "https://gitlab.example/group/project/-/merge_requests/7", "author": {"username": os.environ.get("FAKE_AUTHOR_USER", "author")}, "state": os.environ.get("FAKE_MR_STATE", "opened"), "merged_at": "2026-01-02T00:00:00Z" if os.environ.get("FAKE_MR_STATE") == "merged" else None, "updated_at": "changed" if changed else "fresh", "labels": json.loads(os.environ.get("FAKE_MR_LABELS", "[]")), "diff_refs": {"base_sha": base_sha, "start_sha": start_sha, "head_sha": head_sha}}
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
    value = {"id": 23, "username": os.environ.get("FAKE_CURRENT_USER", "reviewer")}
elif endpoint.startswith("projects/19/merge_requests/7/discussions"):
    value = json.loads(os.environ["FAKE_DISCUSSIONS_JSON"]) if os.environ.get("FAKE_DISCUSSIONS_JSON") else ([{"id": "discussion-42", "notes": [{"id": 42, "system": False, "resolvable": True, "resolved": False, "author": {"username": "other-reviewer"}, "body": "Retry needs an idempotency key", "position": {"head_sha": head_sha, "new_path": changed_path, "new_line": 2}}]}] if os.environ.get("FAKE_DISCUSSION") else [])
elif endpoint.startswith("projects/19/merge_requests/7/notes"):
    value = json.loads(os.environ["FAKE_NOTES_JSON"]) if os.environ.get("FAKE_NOTES_JSON") else []
else:
    value = []
print(json.dumps(value))
"""
            % sys.executable,
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable, state

    def fake_publish_glab(self, directory: Path) -> tuple[Path, Path, Path]:
        state = directory / "fake-publish-state.json"
        state.write_text(
            json.dumps({"labels": [], "discussions": [], "notes": [], "issues": []}),
            encoding="utf-8",
        )
        log = directory / "fake-publish.log"
        executable = directory / "glab"
        executable.write_text(
            """#!%s
import json
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
method = arguments[arguments.index("--method") + 1]
endpoint = arguments[-1]
payload = json.load(sys.stdin) if "--input" in arguments else None
state_path = Path(os.environ["FAKE_PUBLISH_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8"))
Path(os.environ["FAKE_PUBLISH_LOG"]).open("a", encoding="utf-8").write(json.dumps({"argv": arguments, "inherited": os.environ.get("FAKE_INHERITED_OPTION")}) + "\\n")
catalog = json.loads(os.environ["FAKE_LABEL_CATALOG"])
base_sha = os.environ["FAKE_BASE_SHA"]
start_sha = os.environ["FAKE_START_SHA"]
head_sha = os.environ["FAKE_HEAD_SHA"]
if endpoint == "user":
    value = {"id": 23, "username": "reviewer"}
elif endpoint == "projects/group%%2Fproject":
    value = {"id": 19, "path_with_namespace": "group/project"}
elif endpoint.startswith("projects/19/labels"):
    value = catalog
elif endpoint == "projects/19/merge_requests/7" and method == "GET":
    value = {"iid": 7, "web_url": "https://gitlab.example/group/project/-/merge_requests/7", "state": "merged", "labels": state["labels"], "diff_refs": {"base_sha": base_sha, "start_sha": start_sha, "head_sha": head_sha}}
elif endpoint == "projects/19/merge_requests/7" and method == "PUT":
    add = [item for item in payload.get("add_labels", "").split(",") if item]
    remove = {item for item in payload.get("remove_labels", "").split(",") if item}
    state["labels"] = sorted((set(state["labels"]) - remove) | set(add), key=str.casefold)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    value = {"iid": 7, "labels": state["labels"]}
elif endpoint.startswith("projects/19/merge_requests/7/discussions?"):
    value = state["discussions"]
elif endpoint == "projects/19/merge_requests/7/discussions" and method == "POST":
    note = {"id": 101, "system": False, "resolvable": False, "resolved": False, "author": {"id": 23, "username": "reviewer"}, "body": payload["body"], "position": payload.get("position")}
    discussion = {"id": "finding-101", "notes": [note]}
    state["discussions"].append(discussion)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    value = discussion
elif endpoint.startswith("projects/19/merge_requests/7/notes?"):
    value = state["notes"]
elif endpoint == "projects/19/merge_requests/7/discussions/discussion-42/notes" and method == "POST":
    note = {"id": 100, "system": False, "resolvable": False, "resolved": False, "author": {"id": 23, "username": "reviewer"}, "body": payload["body"]}
    state["discussions"][0]["notes"].append(note)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    value = note
elif endpoint == "projects/19/merge_requests/7/discussions/discussion-42" and method == "PUT":
    state["discussions"][0]["notes"][0]["resolved"] = payload["resolved"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    value = state["discussions"][0]
elif endpoint == "projects/19/merge_requests/7/discussions/discussion-42" and method == "GET":
    value = state["discussions"][0]
elif endpoint.startswith("projects/19/issues?"):
    value = state["issues"]
else:
    value = []
print(json.dumps(value))
"""
            % sys.executable,
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable, state, log

    def test_gitlab_runners_support_foreign_cwd_help_and_capabilities(self) -> None:
        for skill in GITLAB_RUNNERS:
            with self.subTest(skill=skill, command="help"):
                self.assertEqual(self.run_runner(skill, "--help").returncode, 0)
            with self.subTest(skill=skill, command="capabilities"):
                result = self.run_runner(skill, "--capabilities")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["schema_version"], 1)

    def test_mutable_gitlab_state_rejects_symlink_target(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py", "canonical_gitlab_state"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.json"
            outside.write_text('{"safe":true}\n', encoding="utf-8")
            target = root / "state.json"
            target.symlink_to(outside)
            with self.assertRaises(module.WorkflowError):
                module.write_json(target, {"safe": False})
            self.assertEqual(outside.read_text(encoding="utf-8"), '{"safe":true}\n')

    def test_review_state_publication_rolls_back_markdown_and_baseline(self) -> None:
        scripts = BUILT_SKILLS / "code-review" / "scripts"
        previous_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "portable_runtime" or name.startswith("portable_runtime.")
        }
        sys.path.insert(0, str(scripts))
        try:
            module = load_module(scripts / "review_context.py", "built_review_context_rollback")
        finally:
            sys.path.remove(str(scripts))
            for name in list(sys.modules):
                if name == "portable_runtime" or name.startswith("portable_runtime."):
                    sys.modules.pop(name)
            sys.modules.update(previous_modules)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            markdown = root / "review-publication.md"
            baseline = root / "review-baseline.json"
            progress = root / "review-current.json"
            markdown.write_text("old review\n", encoding="utf-8")
            baseline.write_text('{"old":true}\n', encoding="utf-8")
            progress_value = module.empty_progress(
                root / "artifacts" / "evidence_snapshot" / f"{'b' * 64}.json",
                "b" * 64,
                mode="normal",
                locale="en",
            )
            progress_value["stage"] = "content_missing"
            module.portable.write_json(progress, progress_value)
            progress_bytes = progress.read_bytes()
            baseline_digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
            real_fsync = os.fsync
            calls = 0

            def fail_after_pointer(descriptor: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("injected directory fsync failure")
                real_fsync(descriptor)

            with patch.object(module.os, "fsync", side_effect=fail_after_pointer):
                with self.assertRaises(OSError):
                    module.publish_review_state(
                        root,
                        "new review\n",
                        root / "artifacts" / "review_plan" / f"{'a' * 64}.json",
                        "a" * 64,
                        {"url": "https://gitlab.example/group/project/-/merge_requests/7"},
                        baseline_digest,
                        {"stage": "content_missing"},
                    )
            self.assertEqual(markdown.read_text(encoding="utf-8"), "old review\n")
            self.assertEqual(baseline.read_text(encoding="utf-8"), '{"old":true}\n')
            self.assertEqual(progress.read_bytes(), progress_bytes)

    def test_line_finding_requires_exactly_one_suggestion(self) -> None:
        scripts = BUILT_SKILLS / "code-review" / "scripts"
        previous_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "portable_runtime" or name.startswith("portable_runtime.")
        }
        sys.path.insert(0, str(scripts))
        try:
            module = load_module(scripts / "review_context.py", "built_review_context_suggestion")
        finally:
            sys.path.remove(str(scripts))
            for name in list(sys.modules):
                if name == "portable_runtime" or name.startswith("portable_runtime."):
                    sys.modules.pop(name)
            sys.modules.update(previous_modules)
        invalid = {
            "finding_id": "finding-1",
            "type": "line",
            "path": "src/example.py",
            "line": 7,
            "old_line": None,
            "body": "Replace this line.",
            "fix_mode": "suggestion",
            "patch": None,
        }
        with self.assertRaises(module.portable.WorkflowError):
            module.validate_finding_publications([invalid], {"finding-1"})
        valid = {
            **invalid,
            "body": "Use the bounded value.\n\n```suggestion:-1+1\nvalue = bounded\n```",
        }
        self.assertEqual(module.validate_finding_publications([valid], {"finding-1"})[0], valid)

        general = {
            **invalid,
            "type": "general",
            "path": None,
            "line": None,
            "body": "Apply the complete fix.",
            "fix_mode": "patch",
            "patch": (
                "diff --git a/src/example.py b/src/example.py\n"
                "--- a/src/example.py\n"
                "+++ b/src/example.py\n"
                "@@ -1 +1 @@\n"
                "-old\n"
                "+new\n"
            ),
        }
        self.assertEqual(module.validate_finding_publications([general], {"finding-1"})[0], general)
        local_fix = {**general, "type": "local_fix", "body": "Apply this local correction."}
        self.assertEqual(
            module.validate_finding_publications([local_fix], {"finding-1"})[0], local_fix
        )

    def test_git_patch_validation_is_exact_head_bounded_and_multi_file(self) -> None:
        scripts = BUILT_SKILLS / "code-review" / "scripts"
        previous_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "portable_runtime" or name.startswith("portable_runtime.")
        }
        sys.path.insert(0, str(scripts))
        try:
            module = load_module(scripts / "review_context.py", "built_review_context_patch")
        finally:
            sys.path.remove(str(scripts))
            for name in list(sys.modules):
                if name == "portable_runtime" or name.startswith("portable_runtime."):
                    sys.modules.pop(name)
            sys.modules.update(previous_modules)
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "commit.gpgsign", "false"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "reviewer@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Example Reviewer"],
                cwd=repository,
                check=True,
            )
            (repository / "one.txt").write_text("one\n", encoding="utf-8")
            (repository / "two.txt").write_text("two\n", encoding="utf-8")
            (repository / "three.txt").write_text("first\nsecond\nthird\n", encoding="utf-8")
            (repository / "é.txt").write_text("accent\n", encoding="utf-8")
            (repository / "link").symlink_to("one.txt")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            patch_text = (
                "diff --git a/one.txt b/one.txt\n"
                "--- a/one.txt\n"
                "+++ b/one.txt\n"
                "@@ -1 +1 @@\n"
                "-one\n"
                "+first\n"
                "diff --git a/two.txt b/two.txt\n"
                "--- a/two.txt\n"
                "+++ b/two.txt\n"
                "@@ -1 +1 @@\n"
                "-two\n"
                "+second\n"
            )
            self.assertEqual(
                module.validate_git_patch(repository, head, patch_text), ["one.txt", "two.txt"]
            )
            quoted_patch = (
                'diff --git "a/\\303\\251.txt" "b/\\303\\251.txt"\n'
                '--- "a/\\303\\251.txt"\n'
                '+++ "b/\\303\\251.txt"\n'
                "@@ -1 +1 @@\n"
                "-accent\n"
                "+changed accent\n"
            )
            self.assertEqual(module.validate_git_patch(repository, head, quoted_patch), ["é.txt"])
            thread_fix = {
                "outcome": "local_fix",
                "proposed_response": "Apply this local correction.",
                "fix_mode": "patch",
                "patch": patch_text,
            }
            module.validate_thread_fix(thread_fix, {}, repository, head)
            (repository / "three.txt").write_text(
                "first\nchanged second\nthird\n", encoding="utf-8"
            )
            subprocess.run(["git", "commit", "-qam", "change middle"], cwd=repository, check=True)
            changed_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            self.assertEqual(
                module.changed_diff_lines(repository, head, changed_head, "three.txt"),
                ({2}, {2}),
            )
            module.validate_suggestion(
                "Use the replacement.\n\n```suggestion:-1+1\nreplacement\n```",
                repo_root=repository,
                head_sha=changed_head,
                path="three.txt",
                line=2,
            )
            with self.assertRaises(module.portable.WorkflowError):
                module.validate_suggestion(
                    "Out of bounds.\n\n```suggestion:-2+1\nreplacement\n```",
                    repo_root=repository,
                    head_sha=changed_head,
                    path="three.txt",
                    line=2,
                )
            with self.assertRaises(module.portable.WorkflowError):
                module.validate_thread_fix(
                    {**thread_fix, "fix_mode": "not_required", "patch": None},
                    {},
                    repository,
                    head,
                )
            self.assertEqual((repository / "one.txt").read_text(encoding="utf-8"), "one\n")
            for invalid in (
                patch_text.replace("-one", "-missing", 1),
                "diff --git a/../secret b/../secret\n--- a/../secret\n+++ b/../secret\n",
                "diff --git a/one.txt b/one.txt\n--- /etc/passwd\n+++ /etc/passwd\n",
                "diff --git a/link b/link\nnew file mode 120000\n--- /dev/null\n+++ b/link\n",
                (
                    "diff --git a/link b/link\n"
                    "--- a/link\n"
                    "+++ b/link\n"
                    "@@ -1 +1 @@\n"
                    "-one.txt\n"
                    "+two.txt\n"
                ),
                (
                    "diff --git a/safe b/safe\n"
                    "--- a/link\n"
                    "+++ b/link\n"
                    "@@ -1 +1 @@\n"
                    "-one.txt\n"
                    "+two.txt\n"
                ),
                'diff --git "a/\\400" "b/\\400"\n--- "a/\\400"\n+++ "b/\\400"\n',
                'diff --git "a/\\000" "b/\\000"\n--- "a/\\000"\n+++ "b/\\000"\n',
                "diff --git a/image.png b/image.png\nGIT binary patch\n",
            ):
                with self.assertRaises(module.portable.WorkflowError):
                    module.validate_git_patch(repository, head, invalid)

    def test_code_review_maps_major_semver_across_complete_label_catalog(self) -> None:
        scripts = BUILT_SKILLS / "code-review" / "scripts"
        previous_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "portable_runtime" or name.startswith("portable_runtime.")
        }
        sys.path.insert(0, str(scripts))
        try:
            module = load_module(scripts / "review_context.py", "built_review_context_labels")
        finally:
            sys.path.remove(str(scripts))
            for name in list(sys.modules):
                if name == "portable_runtime" or name.startswith("portable_runtime."):
                    sys.modules.pop(name)
            sys.modules.update(previous_modules)
        evidence = {
            "labels": {
                "complete": True,
                "items": [
                    {"name": "semver::major", "description": "Breaking compatibility"},
                    {"name": "semver::minor", "description": "Compatible feature"},
                    {"name": "team-owned", "description": "Routing label"},
                ],
            },
            "object": {"labels": ["semver::minor", "team-owned"]},
        }
        assessments = [
            {
                "name": "semver::major",
                "status": "applicable",
                "rationale": "The public contract breaks.",
            },
            {
                "name": "semver::minor",
                "status": "inapplicable",
                "rationale": "Minor understates the compatibility impact.",
            },
            {
                "name": "team-owned",
                "status": "applicable",
                "rationale": "The existing team still owns the change.",
            },
        ]
        result = module.validate_label_assessments(evidence, assessments, "major")
        self.assertEqual(result["add"], ["semver::major"])
        self.assertEqual(result["remove"], ["semver::minor"])
        self.assertEqual(result["semver"]["selected"], "semver::major")
        with self.assertRaises(module.portable.WorkflowError):
            module.validate_label_assessments(evidence, assessments[:-1], "major")

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
        wrong_finalize = self.run_runner(
            "code-review", "finalize", "--evidence", "/tmp/not-an-artifact.json"
        )
        self.assertEqual(wrong_finalize.returncode, 2)
        wrong_payload = json.loads(wrong_finalize.stdout)
        self.assertEqual(wrong_payload["error"]["code"], "invalid_input")
        self.assertIn("--artifact-root", wrong_payload["error"]["message"])

    def mr_content(self, evidence: str, **overrides: Any) -> dict[str, Any]:
        bundle = json.loads(Path(evidence).read_text())["payload"]
        return {
            "locale": bundle["project"].get("locale", "en"),
            "title": "Prepare exact merge request publication plan",
            "description": "## Context\n\nPreserve public behavior.\n\n## Verification\n\nChecks were not run.",
            "change_summary": ["Clarify purpose and report unverified checks."],
            "limitations": [],
            "template": {"id": None, "rationale": "No project template is available."},
            "preservation_notes": [
                "Retained observable behavior; corrected unsupported CI success."
            ],
            "semver_impact": "none",
            "semver_rationale": "No versioned behavior changes in this fixture.",
            "label_assessments": [
                {
                    "name": item["name"],
                    "status": "unresolved",
                    "rationale": "The available evidence does not determine applicability.",
                }
                for item in bundle["labels"]["items"]
            ],
            **overrides,
        }

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
                json.dumps(self.mr_content(evidence)),
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
            self.assertEqual(markdown.name, "mr-publication.md")
            self.assertIn("Pipeline for the current revision: missing", markdown_text)
            self.assertNotIn("Current description", markdown_text)
            self.assertNotIn("Current merge request title", markdown_text)
            self.assertNotIn("Head SHA", markdown_text)
            self.assertIn("glab api --hostname gitlab.example --method PUT", markdown_text)
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

    def test_mr_publication_payloads_labels_locale_and_supersession(self) -> None:
        for locale in ("en", "ru"):
            with (
                self.subTest(locale=locale),
                tempfile.TemporaryDirectory(prefix="mr plan '") as temporary,
            ):
                root = Path(temporary)
                _, state = self.fake_glab(root)
                log = root / "glab.log"
                catalog = [
                    {"name": "type::feature", "description": "Feature"},
                    {"name": "type::security", "description": "Security"},
                    {"name": "obsolete", "description": "No longer applicable"},
                    {"name": "team::docs", "description": "Documentation ownership"},
                ]
                environment = {
                    "XDG_STATE_HOME": str(root / "state"),
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "FAKE_GLAB_STATE": str(state),
                    "FAKE_GLAB_LOG": str(log),
                    "FAKE_LABEL_CATALOG": json.dumps(catalog),
                    "FAKE_MR_LABELS": json.dumps(["type::security", "obsolete"]),
                }
                prepared = self.run_runner(
                    "mr-prepare",
                    "prepare",
                    "--url",
                    "https://gitlab.example/group/project/-/merge_requests/7",
                    "--locale",
                    locale,
                    env=environment,
                )
                self.assertEqual(prepared.returncode, 0, prepared.stdout)
                evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
                description = (
                    "## Контекст\n\nКавычки ' и \"; $(touch NEVER)\n```sh\ncommand --flag\n```\n"
                )
                content = self.mr_content(
                    evidence,
                    description=description,
                    label_assessments=[
                        {
                            "name": item["name"],
                            "status": "unresolved"
                            if item["name"] == "type::security"
                            else "inapplicable"
                            if item["name"] == "obsolete"
                            else "applicable",
                            "rationale": "Confirmed by the collected diff.",
                        }
                        for item in catalog
                    ],
                )
                draft = root / "content.json"
                draft.write_text(json.dumps(content))
                result = self.run_runner(
                    "mr-prepare",
                    "scaffold",
                    "--bundle",
                    evidence,
                    "--content",
                    str(draft),
                    env=environment,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                output = json.loads(result.stdout)
                plan = json.loads(Path(output["artifact_path"]).read_text())["payload"]
                markdown = Path(output["markdown_path"])
                original = markdown.read_bytes()
                self.assertIn(
                    "План обновления MR" if locale == "ru" else "MR update plan", original.decode()
                )
                self.assertIn(description, original.decode())
                payloads = {}
                for request in plan["requests"]:
                    args = shlex.split(request["command"])
                    self.assertEqual(
                        args[:7],
                        [
                            "glab",
                            "api",
                            "--hostname",
                            "gitlab.example",
                            "--method",
                            "PUT",
                            "projects/19/merge_requests/7",
                        ],
                    )
                    payloads[request["field"]] = json.loads(Path(args[-1]).read_text())
                self.assertEqual(payloads["description"], {"description": description})
                self.assertEqual(
                    payloads["labels"],
                    {"add_labels": "team::docs,type::feature", "remove_labels": "obsolete"},
                )
                self.assertIn("type::security", plan["label_review"]["proposed"])
                pointer = markdown.with_suffix(".json")
                finalize_args = shlex.split(
                    plan["markdown"].split("```sh\n")[-1].split("\n```", 1)[0]
                )
                final = self.run_runner("mr-prepare", *finalize_args[2:], env=environment)
                self.assertEqual(final.returncode, 0, final.stdout)
                request_path = Path(shlex.split(plan["requests"][0]["command"])[-1])
                request_bytes = request_path.read_bytes()
                request_path.write_text("{}")
                modified = self.run_runner(
                    "mr-prepare", "finalize", "--plan", str(pointer), env=environment
                )
                self.assertNotEqual(modified.returncode, 0)
                request_path.write_bytes(request_bytes)
                content["locale"] = "ru" if locale == "en" else "en"
                draft.write_text(json.dumps(content))
                invalid = self.run_runner(
                    "mr-prepare",
                    "scaffold",
                    "--bundle",
                    evidence,
                    "--content",
                    str(draft),
                    env=environment,
                )
                self.assertNotEqual(invalid.returncode, 0)
                self.assertEqual(markdown.read_bytes(), original)
                content.update(
                    locale=locale,
                    title="Current merge request title",
                    description="Current description",
                )
                draft.write_text(json.dumps(content))
                replacement = self.run_runner(
                    "mr-prepare",
                    "scaffold",
                    "--bundle",
                    evidence,
                    "--content",
                    str(draft),
                    env=environment,
                )
                self.assertEqual(replacement.returncode, 0, replacement.stdout)
                new = json.loads(Path(json.loads(replacement.stdout)["artifact_path"]).read_text())[
                    "payload"
                ]
                self.assertEqual([item["field"] for item in new["requests"]], ["labels"])
                superseded = self.run_runner(
                    "mr-prepare", "finalize", "--plan", output["artifact_path"], env=environment
                )
                self.assertNotEqual(superseded.returncode, 0)
                old_tab = self.run_runner("mr-prepare", *finalize_args[2:], env=environment)
                self.assertNotEqual(old_tab.returncode, 0)
                self.assertIn("binding is stale", old_tab.stdout)
                self.assertEqual(request_path.read_bytes(), request_bytes)
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertTrue(all(call[call.index("--method") + 1] == "GET" for call in calls))

    def test_mr_template_discovery_selection_and_freshness(self) -> None:
        for names, default, failure in [
            ([], None, False),
            (["Default.md"], None, False),
            (["Feature.md", "Bug.md"], "## Purpose", False),
            ([], None, True),
        ]:
            with (
                self.subTest(names=names, failure=failure),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                _, state = self.fake_glab(root)
                environment = {
                    "XDG_STATE_HOME": str(root / "state"),
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "FAKE_GLAB_STATE": str(state),
                    "FAKE_GLAB_LOG": str(root / "glab.log"),
                    "FAKE_MR_TEMPLATES": json.dumps(names),
                }
                if default:
                    environment["FAKE_MR_DEFAULT_TEMPLATE"] = default
                if failure:
                    environment["FAKE_MR_TEMPLATE_FAILURE"] = "1"
                prepared = self.run_runner(
                    "mr-prepare",
                    "prepare",
                    "--url",
                    "https://gitlab.example/group/project/-/merge_requests/7",
                    env=environment,
                )
                self.assertEqual(prepared.returncode, 0, prepared.stdout)
                evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
                bundle = json.loads(Path(evidence).read_text())["payload"]
                self.assertEqual(bundle["project"]["locale"], "en")
                templates = bundle["project"]["mr_templates"]
                self.assertEqual(templates["complete"], not failure)
                self.assertEqual(len(templates["items"]), len(names) + bool(default))
                selected = (
                    "project-default"
                    if default
                    else f".gitlab/merge_request_templates/{names[0]}"
                    if names
                    else None
                )
                content = self.mr_content(
                    evidence,
                    **({"description": "## Purpose\n\nVerified purpose."} if default else {}),
                    template={
                        "id": selected,
                        "rationale": "Use project default or sole available template.",
                    },
                    limitations=["Template retrieval failed."] if failure else [],
                )
                draft = root / "content.json"
                draft.write_text(json.dumps(content))
                result = self.run_runner(
                    "mr-prepare",
                    "scaffold",
                    "--bundle",
                    evidence,
                    "--content",
                    str(draft),
                    env=environment,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                output = json.loads(result.stdout)
                if selected:
                    missing_heading = {
                        **content,
                        "description": "A summary without the required template headings.",
                    }
                    draft.write_text(json.dumps(missing_heading))
                    invalid_heading = self.run_runner(
                        "mr-prepare",
                        "scaffold",
                        "--bundle",
                        evidence,
                        "--content",
                        str(draft),
                        env=environment,
                    )
                    self.assertNotEqual(invalid_heading.returncode, 0)
                    self.assertIn("template headings", invalid_heading.stdout)
                if failure:
                    self.assertIn(
                        "This does not mean no templates exist",
                        Path(output["markdown_path"]).read_text(),
                    )
                else:
                    final = self.run_runner(
                        "mr-prepare",
                        "finalize",
                        "--plan",
                        output["artifact_path"],
                        env={**environment, "FAKE_MR_DEFAULT_TEMPLATE": "Changed default template"},
                    )
                    self.assertNotEqual(final.returncode, 0)
                    self.assertIn("mr_project", final.stdout)
                content["template"]["id"] = "invented.md"
                draft.write_text(json.dumps(content))
                invalid = self.run_runner(
                    "mr-prepare",
                    "scaffold",
                    "--bundle",
                    evidence,
                    "--content",
                    str(draft),
                    env=environment,
                )
                self.assertNotEqual(invalid.returncode, 0)

    def test_mr_stable_publication_rolls_back_and_partial_run_is_not_success(self) -> None:
        from shared.references.portable_gitlab import contract, mr_publication

        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ):
            root = Path(temporary)
            os.environ["XDG_STATE_HOME"] = str(root / "state")
            _, state = self.fake_glab(root)
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(root / "glab.log"),
            }
            prepared = self.run_runner(
                "mr-prepare",
                "prepare",
                "--url",
                "https://gitlab.example/group/project/-/merge_requests/7",
                env=environment,
            )
            evidence = json.loads(prepared.stdout)["items"][0]["artifact_path"]
            bundle = json.loads(Path(evidence).read_text())["payload"]
            content = self.mr_content(evidence)
            first = mr_publication.scaffold(Path(evidence), bundle, content)
            markdown = Path(first["markdown_path"])
            pointer = markdown.with_suffix(".json")
            previous = (markdown.read_bytes(), pointer.read_bytes())
            real_write = contract.write_bytes
            failed = False

            def fail_once(path: Path, data: bytes) -> None:
                nonlocal failed
                if path == markdown and not failed:
                    failed = True
                    raise OSError("simulated replacement failure")
                real_write(path, data)

            with patch.object(contract, "write_bytes", side_effect=fail_once):
                with self.assertRaises(contract.WorkflowError):
                    mr_publication.scaffold(
                        Path(evidence), bundle, {**content, "title": "A different proposed title"}
                    )
            self.assertEqual((markdown.read_bytes(), pointer.read_bytes()), previous)
            lock = markdown.parent / ".mr-publication.lock"
            self.assertFalse(lock.exists())
            with mr_publication.publication_lock(markdown.parent):
                with self.assertRaises(contract.WorkflowError):
                    mr_publication.scaffold(Path(evidence), bundle, content)
            partial = {**bundle, "retrieval_complete": False}
            source, _ = contract.write_artifact(markdown.parent, "evidence_snapshot", partial)
            result = mr_publication.scaffold(source, partial, content)
            self.assertEqual(result["status"], "incomplete")
            self.assertIsNone(result["markdown_path"])
            self.assertNotIn(str(markdown), result["chat"])
            self.assertEqual((markdown.read_bytes(), pointer.read_bytes()), previous)
            old_format = {
                "title": content["title"],
                "description": content["description"],
                "label_intent": {},
            }
            with self.assertRaisesRegex(contract.WorkflowError, "contract changed"):
                mr_publication.scaffold(Path(evidence), bundle, old_format)

    def test_release_prepare_inventory_artifacts_and_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            for arguments in (
                ("init", "-q"),
                ("config", "commit.gpgsign", "false"),
                ("config", "tag.gpgsign", "false"),
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
                ("config", "commit.gpgsign", "false"),
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
                    ("config", "commit.gpgsign", "false"),
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
                ("config", "commit.gpgsign", "false"),
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

    def test_code_review_collects_jobs_traces_and_downstream_pipelines(self) -> None:
        module = load_module(
            ROOT / "shared/references/portable_gitlab/contract.py", "canonical_gitlab_jobs"
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
            if endpoint.startswith("projects/19/pipelines?sha=c"):
                return [{"id": 41, "sha": "c", "status": "failed"}]
            if endpoint.startswith("projects/19/pipelines/41/jobs"):
                return [{"id": 51, "name": "policy", "stage": "verify", "status": "failed"}]
            if endpoint.startswith("projects/19/pipelines/41/bridges"):
                return [
                    {
                        "id": 52,
                        "name": "downstream",
                        "stage": "verify",
                        "status": "success",
                        "downstream_pipeline": {"id": 42, "project_id": 23},
                    }
                ]
            if endpoint.startswith("projects/23/pipelines/42/jobs"):
                return [{"id": 53, "name": "lint", "stage": "test", "status": "success"}]
            if endpoint.startswith("projects/23/pipelines/42/bridges"):
                return []
            return []

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {"XDG_STATE_HOME": temporary}),
            patch.object(module, "glab_json", side_effect=fake),
            patch.object(
                module,
                "glab_text",
                return_value="Approval count is insufficient\ntoken=hidden-value\n",
            ),
        ):
            bundle = module.collect(target, "code-review")
        self.assertTrue(bundle["retrieval_complete"])
        pipeline = bundle["pipelines"]["items"][0]
        evidence = pipeline["job_evidence"]
        self.assertEqual(len(evidence["pipelines"]), 2)
        trace = evidence["pipelines"][0]["jobs"][0]["trace"]
        self.assertIn("Approval count is insufficient", trace["excerpt"])
        self.assertIn("token=[REDACTED]", trace["excerpt"])
        self.assertNotIn("hidden-value", trace["excerpt"])
        self.assertIn("projects/23/pipelines/42/jobs?per_page=100&page=1", calls)

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
            "unresolved_threads": [{"id": "thread:thread-1"}],
            "responses": [
                {"id": "primary-1", "decision": "reject", "reason": "not applicable"},
                {"id": "critic-1", "decision": "accept", "reason": "confirmed"},
                {"id": "thread:thread-1", "decision": "accept", "reason": "needs resolution"},
            ],
        }
        module.validate_critic(receipt, "evidence")
        with self.assertRaises(module.WorkflowError):
            module.validate_critic(receipt, "evidence", "b" * 64)
        module.validate_critic(
            {**receipt, "scope_digest": "b" * 64, "target_finding_ids": []},
            "evidence",
            "b" * 64,
        )
        with self.assertRaises(module.WorkflowError):
            module.validate_critic({**receipt, "evidence_digest": "other"}, "evidence")
        with self.assertRaises(module.WorkflowError):
            module.validate_critic(
                {key: value for key, value in receipt.items() if key != "external_mutations"},
                "evidence",
            )
        module.validate_decision(report, "evidence", receipt, "deep")
        duplicate_finding = {
            "id": "primary-duplicate",
            "severity": "low",
            "summary": "Documentation contradicts behavior",
            "risk": "Readers rely on the wrong behavior.",
            "evidence": ["docs/example.md:7 contradicts src/example.py:12."],
            "consequence": "Invalid configuration is harder to diagnose.",
            "relation_to_change": "The change adds the contradictory text.",
            "minimum_fix": "Describe the actual behavior.",
        }
        duplicate_receipt = {
            **receipt,
            "findings": [{**duplicate_finding, "id": "critic-duplicate"}],
        }
        duplicate_report = {
            **report,
            "findings": [duplicate_finding],
            "unresolved_threads": [],
            "responses": [
                {"id": "primary-duplicate", "decision": "accept", "reason": "confirmed"},
                {"id": "critic-duplicate", "decision": "accept", "reason": "confirmed"},
            ],
        }
        with self.assertRaisesRegex(module.WorkflowError, "structurally duplicate"):
            module.validate_decision(duplicate_report, "evidence", duplicate_receipt, "deep")
        duplicate_report["responses"][1] = {
            "id": "critic-duplicate",
            "decision": "reject",
            "reason": "duplicates the accepted primary finding",
        }
        module.validate_decision(duplicate_report, "evidence", duplicate_receipt, "deep")
        collision = {
            **report,
            "context_digest": "b" * 64,
            "findings": [{"id": "thread:42"}],
            "unresolved_threads": [{"id": "thread:42"}],
            "responses": [
                {"id": "thread:42", "decision": "accept", "reason": "collision"},
                {"id": "critic-1", "decision": "accept", "reason": "confirmed"},
            ],
        }
        with self.assertRaises(module.WorkflowError):
            module.validate_decision(
                collision,
                "evidence",
                receipt,
                "deep",
                context_digest="b" * 64,
            )
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
            "unresolved_threads": [{"id": "thread:thread"}],
            "responses": [
                {"id": "finding", "decision": "accept", "reason": "confirmed"},
                {"id": "thread:thread", "decision": "reject", "reason": "deferred"},
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

    def test_code_review_verdict_keeps_low_findings_non_blocking(self) -> None:
        scripts = BUILT_SKILLS / "code-review" / "scripts"
        previous_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "portable_runtime" or name.startswith("portable_runtime.")
        }
        sys.path.insert(0, str(scripts))
        try:
            module = load_module(scripts / "review_context.py", "built_review_context_verdict")
        finally:
            sys.path.remove(str(scripts))
            for name in list(sys.modules):
                if name == "portable_runtime" or name.startswith("portable_runtime."):
                    sys.modules.pop(name)
            sys.modules.update(previous_modules)
        low = {
            "id": "docs-1",
            "severity": "low",
            "summary": "Documentation is incomplete",
            "risk": "Readers can miss an option.",
            "evidence": ["README omits the option."],
            "consequence": "Adoption can take longer.",
            "relation_to_change": "The change adds the option.",
            "minimum_fix": "Document the option.",
        }
        evidence = {
            "head_sha": "c",
            "pipelines": {
                "complete": True,
                "items": [{"id": 1, "sha": "c", "status": "failed"}],
            },
        }
        report = {
            "verdict": "blocked",
            "blocking_findings": False,
            "blocking_finding_ids": [],
            "owner_decision_reasons": ["The exact-head pipeline failed."],
        }
        module.validate_review_verdict(report, [low], evidence)
        with self.assertRaises(module.portable.WorkflowError):
            module.validate_review_verdict({**report, "verdict": "not_ready"}, [low], evidence)
        with self.assertRaises(module.portable.WorkflowError):
            module.validate_review_verdict(
                {
                    **report,
                    "blocking_findings": True,
                    "blocking_finding_ids": ["docs-1"],
                    "verdict": "not_ready",
                },
                [low],
                evidence,
            )
        high = {**low, "id": "runtime-1", "severity": "high"}
        successful_evidence = {
            **evidence,
            "pipelines": {
                "complete": True,
                "items": [{"id": 2, "sha": "c", "status": "success"}],
            },
        }
        with self.assertRaises(module.portable.WorkflowError):
            module.validate_review_verdict(
                {
                    "verdict": "ready",
                    "blocking_findings": False,
                    "blocking_finding_ids": [],
                    "owner_decision_reasons": [],
                },
                [high],
                successful_evidence,
            )
        failed_job = {
            "project_id": 19,
            "pipeline_id": 2,
            "id": 7,
            "status": "failed",
            "trace": {
                "complete": True,
                "truncated": False,
                "excerpt": "Merge request requires two approvals.",
                "sha256": "a" * 64,
            },
        }
        job_evidence = {
            "head_sha": "c",
            "pipelines": {
                "complete": True,
                "items": [
                    {
                        "id": 2,
                        "sha": "c",
                        "status": "failed",
                        "job_evidence": {
                            "complete": True,
                            "errors": [],
                            "truncated": False,
                            "pipelines": [
                                {
                                    "project_id": 19,
                                    "pipeline_id": 2,
                                    "jobs": [failed_job],
                                }
                            ],
                        },
                    }
                ],
            },
        }
        process_gate = {
            "project_id": 19,
            "pipeline_id": 2,
            "job_id": 7,
            "classification": "process_gate",
            "rationale": "The job enforces the approval policy rather than code quality.",
            "trace_evidence": "requires two approvals",
        }
        module.validate_review_verdict(
            {
                "verdict": "ready",
                "blocking_findings": False,
                "blocking_finding_ids": [],
                "owner_decision_reasons": [],
                "ci_job_assessments": [process_gate],
            },
            [low],
            job_evidence,
        )
        with self.assertRaises(module.portable.WorkflowError):
            module.validate_review_verdict(
                {
                    "verdict": "ready",
                    "blocking_findings": False,
                    "blocking_finding_ids": [],
                    "owner_decision_reasons": [],
                    "ci_job_assessments": [
                        {
                            **process_gate,
                            "classification": "code_failure",
                            "rationale": "The test assertion failed.",
                        }
                    ],
                },
                [low],
                job_evidence,
            )
        raw_head = "a" * 40
        with self.assertRaises(module.portable.WorkflowError):
            module.reject_visible_raw_refs(
                f"Changed behavior at {raw_head}", {"head_sha": raw_head}
            )
        previous_head = "b" * 40
        with self.assertRaises(module.portable.WorkflowError):
            module.reject_visible_raw_refs(
                f"Compared from {previous_head}",
                {"head_sha": raw_head},
                {
                    "incremental": {
                        "incremental_delta": {
                            "from_head": previous_head,
                            "to_head": raw_head,
                        }
                    }
                },
            )

    def test_review_content_template_accounts_for_fifty_three_threads(self) -> None:
        scripts = BUILT_SKILLS / "code-review" / "scripts"
        previous_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "portable_runtime" or name.startswith("portable_runtime.")
        }
        sys.path.insert(0, str(scripts))
        try:
            module = load_module(scripts / "review_context.py", "built_review_context_template")
        finally:
            sys.path.remove(str(scripts))
            for name in list(sys.modules):
                if name == "portable_runtime" or name.startswith("portable_runtime."):
                    sys.modules.pop(name)
            sys.modules.update(previous_modules)
        discussions = [
            {
                "id": f"discussion-{index}",
                "root_note_id": index,
                "root_note_url": f"https://gitlab.example/mr#note_{index}",
                "root_system": False,
                "root_resolvable": True,
                "root_resolved": False,
                "notes": [{"id": index, "system": False, "body": f"thread {index}"}],
            }
            for index in range(1, 50)
        ]
        discussions.extend(
            [
                {
                    "id": "closed-by-other",
                    "root_note_id": 50,
                    "root_note_url": "https://gitlab.example/mr#note_50",
                    "root_system": False,
                    "root_resolvable": True,
                    "root_resolved": True,
                    "root_resolved_by_username": "other-reviewer",
                    "notes": [
                        {
                            "id": 50,
                            "system": False,
                            "body": "fixed",
                            "author": {"username": "other-reviewer"},
                        }
                    ],
                },
                {
                    "id": "closed-with-own-conclusion",
                    "root_note_id": 51,
                    "root_note_url": "https://gitlab.example/mr#note_51",
                    "root_system": False,
                    "root_resolvable": True,
                    "root_resolved": True,
                    "root_resolved_by_username": "reviewer",
                    "notes": [
                        {
                            "id": 51,
                            "system": False,
                            "body": "confirmed fixed",
                            "author": {"username": "reviewer"},
                        }
                    ],
                },
                {
                    "id": "reply-after-own-close",
                    "root_note_id": 52,
                    "root_note_url": "https://gitlab.example/mr#note_52",
                    "root_system": False,
                    "root_resolvable": True,
                    "root_resolved": True,
                    "root_resolved_by_username": "reviewer",
                    "notes": [
                        {
                            "id": 52,
                            "system": False,
                            "body": "confirmed fixed",
                            "author": {"username": "reviewer"},
                        },
                        {
                            "id": 152,
                            "system": False,
                            "body": "this still fails",
                            "author": {"username": "other-reviewer"},
                        },
                    ],
                },
                {
                    "id": "closed-by-unknown",
                    "root_note_id": 53,
                    "root_note_url": "https://gitlab.example/mr#note_53",
                    "root_system": False,
                    "root_resolvable": True,
                    "root_resolved": True,
                    "root_resolved_by_username": None,
                    "notes": [
                        {
                            "id": 53,
                            "system": False,
                            "body": "confirmed fixed",
                            "author": {"username": "reviewer"},
                        }
                    ],
                },
            ]
        )
        context = {
            "role": "reviewer",
            "current_user_username": "reviewer",
            "discussions": discussions,
            "notes": [],
            "publication_markers": [],
            "issue_templates": [],
            "release_evidence": {"target_branch": "main", "target_sha": "b"},
            "incremental": {
                "previous_findings": [],
                "previous_recommended_issues": [],
                "reconsidered_rejected_candidates": [],
            },
        }
        evidence = {
            "labels": {"complete": True, "items": []},
            "object": {"labels": []},
        }
        value = module.content_template(
            evidence,
            context,
            {"findings": [], "critic_findings": [], "responses": [], "accepted_findings": []},
            "en",
        )
        self.assertEqual(len(value["thread_decisions"]), 53)
        self.assertEqual(
            {item["id"] for item in value["thread_decisions"]},
            {str(index) for index in range(1, 54)},
        )
        self.assertTrue(
            all(len(item["last_note_body_sha256"]) == 64 for item in value["thread_decisions"])
        )
        self.assertTrue(all(len(item["thread_sha256"]) == 64 for item in value["thread_decisions"]))
        outcomes = {item["id"]: item["outcome"] for item in value["thread_decisions"]}
        self.assertEqual(outcomes["50"], "reply")
        self.assertEqual(outcomes["51"], "reply")
        self.assertEqual(outcomes["52"], "reply")
        self.assertEqual(outcomes["53"], "reply")

    def test_recommended_issue_uses_exact_head_project_template(self) -> None:
        scripts = BUILT_SKILLS / "code-review" / "scripts"
        previous_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "portable_runtime" or name.startswith("portable_runtime.")
        }
        sys.path.insert(0, str(scripts))
        try:
            module = load_module(scripts / "review_context.py", "built_review_issue_templates")
        finally:
            sys.path.remove(str(scripts))
            for name in list(sys.modules):
                if name == "portable_runtime" or name.startswith("portable_runtime."):
                    sys.modules.pop(name)
            sys.modules.update(previous_modules)
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "commit.gpgsign", "false"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "reviewer@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Example Reviewer"],
                cwd=repository,
                check=True,
            )
            template = repository / ".gitlab" / "issue_templates" / "отчёт об ошибке.md"
            template.parent.mkdir(parents=True)
            template.write_text("## Problem\n\n## Expected behavior\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "template"], cwd=repository, check=True)
            head_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            templates = module.project_issue_templates(
                {
                    "complete": True,
                    "repo_root": str(repository),
                    "refs": {"head_sha": head_sha},
                }
            )
            self.assertEqual(templates[0]["path"], ".gitlab/issue_templates/отчёт об ошибке.md")
            issue = {
                "id": "bug-1",
                "title": "Fix the bug",
                "problem": "The operation fails.",
                "risk": "Users cannot complete it.",
                "evidence": ["The exact reviewed path returns an error."],
                "reason_out_of_scope": "The failing path predates this MR.",
                "minimum_fix": "Handle the failing operation.",
                "body": "## Problem\n\nThe operation fails.\n\n## Expected behavior\n\nIt succeeds.",
                "template_path": ".gitlab/issue_templates/отчёт об ошибке.md",
            }
            self.assertEqual(module.validate_recommended_issues([issue], templates), [issue])
            with self.assertRaises(module.portable.WorkflowError):
                module.validate_recommended_issues([{**issue, "template_path": None}], templates)

    def test_incomplete_review_context_does_not_advance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            for arguments in (
                ("init", "-q"),
                ("config", "commit.gpgsign", "false"),
                ("config", "user.email", "reviewer@example.invalid"),
                ("config", "user.name", "Example Reviewer"),
            ):
                subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
            (repository / "review.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "review.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            _glab, state = self.fake_glab(root)
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(root / "glab.log"),
                "FAKE_BASE_SHA": revision,
                "FAKE_START_SHA": revision,
                "FAKE_HEAD_SHA": revision,
                "FAKE_CHANGED_PATH": "server-only.txt",
            }
            target = "https://gitlab.example/group/project/-/merge_requests/7"
            prepared = self.run_runner(
                "code-review",
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                env=environment,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            prepared_payload = json.loads(prepared.stdout)
            context = self.run_runner(
                "code-review",
                *prepared_payload["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(context.returncode, 2)
            context_payload = json.loads(context.stdout)
            self.assertEqual(context_payload["stage"], "prepared")
            self.assertEqual(context_payload["next_action"]["argv"][2], "context")
            status = self.run_runner(
                "code-review",
                "status",
                "--artifact-root",
                prepared_payload["items"][0]["artifact_root"],
                env=environment,
            )
            self.assertEqual(json.loads(status.stdout)["stage"], "prepared")

    def test_fast_review_skips_critic_and_irrecoverable_evidence_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            for arguments in (
                ("init", "-q"),
                ("config", "commit.gpgsign", "false"),
                ("config", "user.email", "reviewer@example.invalid"),
                ("config", "user.name", "Example Reviewer"),
            ):
                subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
            (repository / "review.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "review.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            _glab, state = self.fake_glab(root)
            environment = {
                "XDG_STATE_HOME": str(root / "state"),
                "PATH": f"{root}:{os.environ['PATH']}",
                "FAKE_GLAB_STATE": str(state),
                "FAKE_GLAB_LOG": str(root / "glab.log"),
                "FAKE_BASE_SHA": revision,
                "FAKE_START_SHA": revision,
                "FAKE_HEAD_SHA": revision,
            }
            target = "https://gitlab.example/group/project/-/merge_requests/7"
            prepared = self.run_runner(
                "code-review",
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                "--review-mode",
                "fast",
                env=environment,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            prepared_payload = json.loads(prepared.stdout)
            context = self.run_runner(
                "code-review",
                *prepared_payload["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            context_payload = json.loads(context.stdout)
            self.assertEqual(context_payload["review_mode"], "fast")
            self.assertEqual(context_payload["next_action"]["argv"][2], "finalize")
            artifact_root = prepared_payload["items"][0]["artifact_root"]
            status = self.run_runner(
                "code-review", "status", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(json.loads(status.stdout)["stage"], "finalize_missing")
            finalized = self.run_runner(
                "code-review", "finalize", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            Path(prepared_payload["items"][0]["artifact_path"]).unlink()
            blocked = self.run_runner(
                "code-review", "report-review", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(blocked.returncode, 4)
            blocked_payload = json.loads(blocked.stdout)
            self.assertEqual(blocked_payload["stage"], "stale")
            self.assertIsNone(blocked_payload["next_action"])

    def test_runner_final_review_requires_bound_current_finalize_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            for arguments in (
                ("init", "-q"),
                ("config", "commit.gpgsign", "false"),
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
            prepared = self.run_runner(
                "code-review",
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                "--review-mode",
                "deep",
                "--locale",
                "en",
                env=environment,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            prepared_payload = json.loads(prepared.stdout)
            self.assertEqual(prepared_payload["items"][0]["stage"], "prepared")
            self.assertEqual(prepared_payload["items"][0]["next_action"]["argv"][2], "context")
            evidence = prepared_payload["items"][0]["artifact_path"]
            self.assertTrue(
                json.loads(prepared.stdout)["items"][0]["complete"], Path(evidence).read_text()
            )
            evidence_digest = hashlib.sha256(Path(evidence).read_bytes()).hexdigest()
            artifact_root = json.loads(prepared.stdout)["items"][0]["artifact_root"]
            next_status = self.run_runner(
                "code-review", "next", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(next_status.returncode, 0, next_status.stderr)
            self.assertEqual(json.loads(next_status.stdout)["stage"], "prepared")
            context_result = self.run_runner(
                "code-review",
                *prepared_payload["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(context_result.returncode, 0, context_result.stderr)
            context = json.loads(context_result.stdout)
            self.assertEqual(context["role"], "reviewer")
            self.assertEqual(context["counts"]["open_resolvable"], 1)
            self.assertEqual(context["next_action"]["argv"][2], "template-review")
            context_digest = context["digest"]
            context_path = context["artifact_path"]
            replayed_context = self.run_runner(
                "code-review",
                *prepared_payload["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(replayed_context.returncode, 2)
            replay_status = self.run_runner(
                "code-review", "status", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(json.loads(replay_status.stdout)["stage"], "critic_missing")
            critic_template_result = self.run_runner(
                "code-review",
                "template-review",
                "--artifact-root",
                artifact_root,
                "--kind",
                "critic",
                env=environment,
            )
            self.assertEqual(critic_template_result.returncode, 0, critic_template_result.stderr)
            critic_template = json.loads(
                Path(json.loads(critic_template_result.stdout)["template_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(critic_template["run_id"], "")
            self.assertEqual(critic_template["evidence_digest"], evidence_digest)
            primary_finding = {
                "id": "primary-1",
                "severity": "high",
                "summary": "Retry can repeat the external operation",
                "risk": "A retry can execute the operation twice.",
                "evidence": ["The current retry path calls the provider before reserving an ID."],
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
            unrecorded_status = self.run_runner(
                "code-review", "status", "--artifact-root", artifact_root, env=environment
            )
            unrecorded_payload = json.loads(unrecorded_status.stdout)
            self.assertEqual(
                unrecorded_payload.get("resume_stage") or unrecorded_payload["stage"],
                "critic_missing",
            )
            recorded_receipt = self.run_runner(
                "code-review",
                "record-artifact",
                "--kind",
                "critic_receipt",
                "--evidence",
                evidence,
                "--input",
                str(receipt),
                env=environment,
            )
            self.assertEqual(recorded_receipt.returncode, 0, recorded_receipt.stderr)
            recorded_payload = json.loads(recorded_receipt.stdout)
            self.assertEqual(recorded_payload["next_action"]["argv"][2], "finalize")
            receipt_artifact = recorded_payload["artifact_path"]
            receipt_artifact_digest = recorded_payload["digest"]
            finalized = self.run_runner(
                "code-review", "finalize", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(finalized.returncode, 0, finalized.stdout + finalized.stderr)
            finalized_payload = json.loads(finalized.stdout)
            self.assertEqual(finalized_payload["next_action"]["argv"][2], "template-review")
            finalize_digest = finalized_payload["digest"]
            finalize_report = finalized_payload["artifact_path"]
            decision_template_result = self.run_runner(
                "code-review",
                "template-review",
                "--artifact-root",
                artifact_root,
                "--kind",
                "decision",
                env=environment,
            )
            self.assertEqual(
                decision_template_result.returncode, 0, decision_template_result.stderr
            )
            decision_template = json.loads(
                Path(json.loads(decision_template_result.stdout)["template_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(decision_template["context_digest"], context_digest)
            self.assertEqual(decision_template["unresolved_threads"], [{"id": "thread:42"}])
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
                        "critic_receipt_digest": receipt_artifact_digest,
                        "verdict": "not_ready",
                        "blocking_findings": True,
                        "blocking_finding_ids": ["primary-1"],
                        "owner_decision_reasons": [],
                        "run_id": "primary-run",
                        "session_id": "primary-session",
                        "findings": [primary_finding],
                        "unresolved_threads": [{"id": "thread:42"}],
                        "responses": [
                            {"id": "primary-1", "decision": "accept", "reason": "confirmed"},
                            {
                                "id": "critic-1",
                                "decision": "reject",
                                "reason": "outside the changed contract",
                            },
                            {"id": "thread:42", "decision": "accept", "reason": "still open"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            raw_receipt_review = self.run_runner(
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
            self.assertEqual(raw_receipt_review.returncode, 2)
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
                receipt_artifact,
                "--finalize-report",
                finalize_report,
                "--mode",
                "deep",
                env=environment,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            reviewed_result = json.loads(reviewed.stdout)
            self.assertFalse(reviewed_result["external_mutations"])
            content_template_result = self.run_runner(
                "code-review",
                "template-review",
                "--artifact-root",
                artifact_root,
                "--kind",
                "content",
                env=environment,
            )
            self.assertEqual(content_template_result.returncode, 0, content_template_result.stderr)
            generated_content = json.loads(
                Path(json.loads(content_template_result.stdout)["template_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertNotIn("presentation", generated_content)
            self.assertEqual(len(generated_content["thread_decisions"]), 1)
            self.assertEqual(len(generated_content["label_assessments"]), 4)
            review_content = root / "review-content.json"
            review_content.write_text(
                json.dumps(
                    {
                        "locale": "en",
                        "chat_assessment": {
                            "necessity": {
                                "status": "supported",
                                "rationale": "The retry defect is confirmed.",
                            },
                            "relevance": {
                                "status": "current",
                                "rationale": "The exact reviewed head is current.",
                            },
                            "change": "The MR adds retry behavior but does not reserve an idempotency key before the external call.",
                        },
                        "summary": "The change is small and preserves the reviewed contract.",
                        "architecture_assessment": "The responsibility remains with its existing owner.",
                        "semver_impact": "patch",
                        "semver_rationale": "The fix changes behavior without changing the public API.",
                        "semver_assessment": {
                            **generated_content["semver_assessment"],
                            "policy": "No release policy was found in the fixture.",
                            "sources": ["Fixture repository and empty release catalog"],
                            "fallback_reason": "No confirmed release is available.",
                        },
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
                        "label_assessments": [
                            {
                                "name": "next-compatible",
                                "status": "inapplicable",
                                "rationale": "The change is a patch, not a minor release.",
                            },
                            {
                                "name": "semver::major",
                                "status": "inapplicable",
                                "rationale": "The change is backward compatible.",
                            },
                            {
                                "name": "semver::patch",
                                "status": "applicable",
                                "rationale": "The reviewed fix has patch SemVer impact.",
                            },
                            {
                                "name": "ship-ready",
                                "status": "inapplicable",
                                "rationale": "This MR is not a release publication.",
                            },
                        ],
                        "checks": ["Compared the exact base and head revisions."],
                        "findings": [primary_finding],
                        "finding_publications": [
                            {
                                "finding_id": "primary-1",
                                "type": "general",
                                "path": None,
                                "line": None,
                                "old_line": None,
                                "body": "You need to reserve an idempotency key before the external call.",
                                "fix_mode": "patch",
                                "patch": (
                                    "diff --git a/review.txt b/review.txt\n"
                                    "--- a/review.txt\n"
                                    "+++ b/review.txt\n"
                                    "@@ -1,2 +1,3 @@\n"
                                    " base\n"
                                    " reviewed change\n"
                                    "+reserve idempotency key\n"
                                ),
                            }
                        ],
                        "previous_finding_assessments": [],
                        "issue_templates": [],
                        "recommended_issues": [
                            {
                                "id": "issue-1",
                                "title": "Track retry exhaustion observability",
                                "problem": "The broader retry subsystem lacks a terminal signal.",
                                "risk": "Operators cannot distinguish retry exhaustion.",
                                "evidence": ["The existing subsystem has no terminal metric."],
                                "reason_out_of_scope": "The subsystem is not changed by this MR.",
                                "minimum_fix": "Add the existing terminal retry metric separately.",
                                "body": "Track a terminal metric for retry exhaustion in the broader subsystem.",
                                "template_path": None,
                            }
                        ],
                        "rejected_candidates": [
                            {
                                "id": "critic-1",
                                "source": "critic",
                                "finding": critic_finding,
                                "reason": "The broader observability gap is outside this MR.",
                                "paths": ["review.txt"],
                                "thread_ids": [],
                                "metadata_fields": [],
                                "ci": False,
                            }
                        ],
                        "rejected_candidate_assessments": [],
                        "thread_decisions": [
                            {
                                "id": "42",
                                "url": f"{target}#note_42",
                                "state": "open",
                                "assessment": "fixed",
                                "rationale": "The existing thread can be acknowledged and resolved.",
                                "outcome": "resolve",
                                "proposed_response": "I tracked the remaining risk in the current finding. Closing.",
                                "fix_mode": "not_required",
                                "patch": None,
                                "fixing_commit": None,
                                "last_note_id": 42,
                                "last_note_body_sha256": hashlib.sha256(
                                    b"Retry needs an idempotency key"
                                ).hexdigest(),
                                "thread_sha256": generated_content["thread_decisions"][0][
                                    "thread_sha256"
                                ],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            invalid_content = json.loads(review_content.read_text(encoding="utf-8"))
            invalid_content["thread_decisions"][0].update(
                {"state": "resolved", "outcome": "no_publication", "proposed_response": None}
            )
            invalid_content_path = root / "invalid-review-content.json"
            invalid_content_path.write_text(json.dumps(invalid_content), encoding="utf-8")
            invalid_plan = self.run_runner(
                "code-review",
                "scaffold-review",
                "--evidence",
                evidence,
                "--context",
                context_path,
                "--decision",
                reviewed_result["artifact_path"],
                "--content",
                str(invalid_content_path),
                env=environment,
            )
            self.assertEqual(invalid_plan.returncode, 2)
            self.assertIn("state does not match", invalid_plan.stderr)
            invalid_accepted = json.loads(review_content.read_text(encoding="utf-8"))
            invalid_accepted["thread_decisions"][0].update(
                {"assessment": "accepted", "outcome": "reply", "fix_mode": "not_required"}
            )
            invalid_accepted_path = root / "invalid-accepted-content.json"
            invalid_accepted_path.write_text(json.dumps(invalid_accepted), encoding="utf-8")
            invalid_accepted_plan = self.run_runner(
                "code-review",
                "scaffold-review",
                "--evidence",
                evidence,
                "--context",
                context_path,
                "--decision",
                reviewed_result["artifact_path"],
                "--content",
                str(invalid_accepted_path),
                env=environment,
            )
            self.assertEqual(invalid_accepted_plan.returncode, 2)
            self.assertIn("accepted thread requires", invalid_accepted_plan.stderr)
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
            outline = "\n".join(
                line for line in markdown.splitlines() if line.startswith(("# ", "## "))
            )
            self.assertEqual(
                outline,
                (ROOT / "tests/fixtures/code-review/reviewer-plan.outline")
                .read_text(encoding="utf-8")
                .strip(),
            )
            self.assertEqual(Path(plan_result["markdown_path"]).name, "review-publication.md")
            self.assertIn("Retry can repeat the external operation", markdown)
            self.assertIn(
                "The current retry path calls the provider before reserving an ID.", markdown
            )
            self.assertIn("The reviewed change adds the retry path.", markdown)
            self.assertIn(f"{target}#note_42", markdown)
            self.assertIn("MR metadata", markdown)
            self.assertIn("The fix changes behavior without changing the public API.", markdown)
            self.assertIn("git apply <<'PATCH'", markdown)
            release = json.loads((ROOT / "packages/skills/package.json").read_text())["version"]
            self.assertIn(f"code-review: {release} · contract: 6", markdown)
            self.assertNotIn("`operation:", markdown)
            self.assertNotIn("`position:", markdown)
            self.assertNotIn("## Manual publication", markdown)
            self.assertNotIn(base_sha, markdown)
            self.assertNotIn(head_sha, markdown)
            self.assertEqual(len(plan_result["publication_body_paths"]), 3)
            body_path = Path(plan_result["publication_body_paths"][0])
            self.assertTrue(body_path.is_absolute())
            self.assertTrue(body_path.is_file())
            bodies = [
                Path(value).read_text(encoding="utf-8")
                for value in plan_result["publication_body_paths"]
            ]
            self.assertTrue(all("<!-- code-review:id=" not in value for value in bodies))
            patch_body = next(value for value in bodies if "diff --git" in value)
            self.assertIn("```sh\ngit apply <<'PATCH'\n", patch_body)
            self.assertIn("\nPATCH\n```", patch_body)
            self.assertNotIn("```diff", patch_body)
            commands = plan_result["publication_commands"]
            self.assertEqual(len(commands), 5)
            self.assertTrue(all(value.startswith("glab ") for value in commands))
            self.assertTrue(all("review_publish.py" not in value for value in commands))
            plan_document = json.loads(
                Path(plan_result["artifact_path"]).read_text(encoding="utf-8")
            )
            preview = plan_document["payload"]["publication_preview"]
            thread_actions = [item for item in preview["actions"] if item["kind"] == "thread"]
            self.assertEqual([item["operation"] for item in thread_actions], ["reply", "resolve"])
            self.assertIn("--method POST", thread_actions[0]["command"])
            self.assertIn("/notes", thread_actions[0]["command"])
            self.assertIn("--method PUT", thread_actions[1]["command"])
            self.assertIn("resolved=true", thread_actions[1]["command"])
            self.assertTrue(all("&&" not in item["command"] for item in thread_actions))
            label_action = next(item for item in preview["actions"] if item["kind"] == "labels")
            self.assertIn("--label semver::patch", label_action["command"])
            self.assertEqual(
                plan_document["payload"]["label_review"]["semver"]["selected"], "semver::patch"
            )
            self.assertEqual(plan_document["payload"]["review_contract_version"], 6)
            report = self.run_runner(
                "code-review", "report-review", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(report.returncode, 0, report.stderr)
            report_payload = json.loads(report.stdout)
            self.assertEqual(report_payload["stage"], "plan_ready")
            self.assertIn(plan_result["markdown_path"], report_payload["chat"])
            self.assertIn("### MR assessment", report_payload["chat"])
            self.assertNotIn(primary_finding["summary"], report_payload["chat"])
            self.assertNotIn(primary_finding["evidence"][0], report_payload["chat"])
            (Path(artifact_root) / "current.json").write_text(
                json.dumps(
                    {
                        "evidence_path": "/unrelated/profile/evidence.json",
                        "evidence_digest": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            still_active = self.run_runner(
                "code-review", "report-review", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(still_active.returncode, 0, still_active.stderr)
            self.assertTrue((Path(artifact_root) / "review-baseline.json").is_file())
            unchanged_prepared = self.run_runner(
                "code-review",
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                env=environment,
            )
            self.assertEqual(unchanged_prepared.returncode, 0, unchanged_prepared.stderr)
            unchanged_prepared_payload = json.loads(unchanged_prepared.stdout)
            unchanged_context = self.run_runner(
                "code-review",
                *unchanged_prepared_payload["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(unchanged_context.returncode, 0, unchanged_context.stderr)
            unchanged = json.loads(unchanged_context.stdout)["incremental"]
            self.assertEqual(unchanged["mode"], "unchanged")
            self.assertFalse(unchanged["critic_required"])
            self.assertEqual(json.loads(unchanged_context.stdout)["review_mode"], "unchanged")
            self.assertEqual(
                json.loads(unchanged_context.stdout)["next_action"]["argv"][2], "finalize"
            )
            unchanged_context_payload = json.loads(unchanged_context.stdout)
            unchanged_finalized = self.run_runner(
                "code-review", "finalize", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(unchanged_finalized.returncode, 0, unchanged_finalized.stderr)
            unchanged_finalize_payload = json.loads(unchanged_finalized.stdout)
            unchanged_decision_template = self.run_runner(
                "code-review",
                "template-review",
                "--artifact-root",
                artifact_root,
                "--kind",
                "decision",
                env=environment,
            )
            self.assertEqual(
                unchanged_decision_template.returncode, 0, unchanged_decision_template.stderr
            )
            unchanged_decision = json.loads(
                Path(json.loads(unchanged_decision_template.stdout)["template_path"]).read_text(
                    encoding="utf-8"
                )
            )
            unchanged_decision.update(
                {
                    "run_id": "unchanged-run",
                    "session_id": "unchanged-session",
                    "verdict": "not_ready",
                    "blocking_findings": True,
                    "blocking_finding_ids": ["primary-1"],
                    "findings": [primary_finding],
                    "responses": [
                        {"id": "thread:42", "decision": "accept", "reason": "still reviewed"},
                        {"id": "primary-1", "decision": "accept", "reason": "still active"},
                    ],
                }
            )
            unchanged_decision_path = root / "unchanged-decision.json"
            unchanged_decision_path.write_text(json.dumps(unchanged_decision), encoding="utf-8")
            unchanged_reviewed = self.run_runner(
                "code-review",
                "finalize-review",
                "--evidence",
                unchanged_prepared_payload["items"][0]["artifact_path"],
                "--report",
                str(unchanged_decision_path),
                "--context",
                unchanged_context_payload["artifact_path"],
                "--finalize-report",
                unchanged_finalize_payload["artifact_path"],
                "--mode",
                "unchanged",
                env=environment,
            )
            self.assertEqual(unchanged_reviewed.returncode, 0, unchanged_reviewed.stderr)
            unchanged_content_template = self.run_runner(
                "code-review",
                "template-review",
                "--artifact-root",
                artifact_root,
                "--kind",
                "content",
                env=environment,
            )
            self.assertEqual(
                unchanged_content_template.returncode, 0, unchanged_content_template.stderr
            )
            unchanged_template_content = json.loads(
                Path(json.loads(unchanged_content_template.stdout)["template_path"]).read_text(
                    encoding="utf-8"
                )
            )
            unchanged_content = json.loads(review_content.read_text(encoding="utf-8"))
            unchanged_content["thread_decisions"] = unchanged_template_content["thread_decisions"]
            unchanged_content["rejected_candidates"] = unchanged_template_content[
                "rejected_candidates"
            ]
            unchanged_content["rejected_candidate_assessments"] = unchanged_template_content[
                "rejected_candidate_assessments"
            ]
            unchanged_content["thread_decisions"][0].update(
                {
                    "assessment": "fixed",
                    "rationale": "The thread was rechecked in the unchanged audit.",
                    "outcome": "resolve",
                    "proposed_response": "The current code still matches the checked result. Closing.",
                }
            )
            unchanged_content["previous_finding_assessments"] = [
                {
                    "id": "primary-1",
                    "kind": "finding",
                    "status": "active",
                    "previous_status": "active",
                    "current_status": "active",
                    "rationale": "The finding remains valid in the unchanged audit.",
                    "action": "No changed publication is needed.",
                    "publication_action": "no_publication",
                    "publication_body": None,
                    "critic_required": False,
                },
                {
                    "id": "issue-1",
                    "kind": "issue",
                    "status": "active",
                    "previous_status": "active",
                    "current_status": "active",
                    "rationale": "The separate issue remains outside this MR.",
                    "action": "No issue update is needed.",
                    "publication_action": "no_publication",
                    "publication_body": None,
                    "critic_required": False,
                },
            ]
            unchanged_content_path = root / "unchanged-content.json"
            unchanged_content_path.write_text(json.dumps(unchanged_content), encoding="utf-8")
            unchanged_plan = self.run_runner(
                "code-review",
                "scaffold-review",
                "--evidence",
                unchanged_prepared_payload["items"][0]["artifact_path"],
                "--context",
                unchanged_context_payload["artifact_path"],
                "--decision",
                json.loads(unchanged_reviewed.stdout)["artifact_path"],
                "--content",
                str(unchanged_content_path),
                env=environment,
            )
            self.assertEqual(unchanged_plan.returncode, 0, unchanged_plan.stderr)
            unchanged_plan_document = json.loads(
                Path(json.loads(unchanged_plan.stdout)["artifact_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(unchanged_plan_document["payload"]["mode"], "unchanged")
            unchanged_report = self.run_runner(
                "code-review", "report-review", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(unchanged_report.returncode, 0, unchanged_report.stderr)
            self.assertEqual(json.loads(unchanged_report.stdout)["stage"], "plan_ready")
            baseline_path = Path(artifact_root) / "review-baseline.json"
            baseline_bytes = baseline_path.read_bytes()
            baseline_path.unlink()
            missing_baseline_report = self.run_runner(
                "code-review", "report-review", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(missing_baseline_report.returncode, 4)
            missing_baseline_payload = json.loads(missing_baseline_report.stdout)
            self.assertEqual(missing_baseline_payload["stage"], "content_missing")
            self.assertEqual(
                missing_baseline_payload["next_action"]["argv"][2],
                "template-review",
            )
            baseline_path.write_bytes(baseline_bytes)
            full_prepared = self.run_runner(
                "code-review",
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                "--incremental",
                "off",
                env=environment,
            )
            self.assertEqual(full_prepared.returncode, 0, full_prepared.stderr)
            full_prepared_payload = json.loads(full_prepared.stdout)
            full_action = full_prepared_payload["items"][0]["next_action"]["argv"]
            self.assertEqual(full_action[full_action.index("--incremental") + 1], "off")
            full_context = self.run_runner(
                "code-review",
                *full_prepared_payload["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(full_context.returncode, 0, full_context.stderr)
            self.assertEqual(json.loads(full_context.stdout)["incremental"]["mode"], "full")
            finding_body = next(value for value in bodies if "idempotency key" in value)
            published_discussions = [
                {
                    "id": "discussion-42",
                    "notes": [
                        {
                            "id": 42,
                            "system": False,
                            "resolvable": True,
                            "resolved": False,
                            "author": {"username": "other-reviewer"},
                            "body": "Retry needs an idempotency key",
                            "position": {
                                "head_sha": head_sha,
                                "new_path": "review.txt",
                                "new_line": 2,
                            },
                        }
                    ],
                },
                {
                    "id": "published-primary-1",
                    "notes": [
                        {
                            "id": 99,
                            "system": False,
                            "resolvable": False,
                            "resolved": False,
                            "author": {"username": "reviewer"},
                            "body": finding_body,
                        }
                    ],
                },
            ]
            published_discussions_json = json.dumps(published_discussions)
            environment["FAKE_DISCUSSIONS_JSON"] = published_discussions_json
            marked_prepared = self.run_runner(
                "code-review", "prepare", "--url", target, env=environment
            )
            self.assertEqual(marked_prepared.returncode, 0, marked_prepared.stderr)
            marked_evidence = json.loads(marked_prepared.stdout)["items"][0]["artifact_path"]
            marked_context = self.run_runner(
                "code-review",
                "context",
                "--evidence",
                marked_evidence,
                "--repo-root",
                str(repository),
                env=environment,
            )
            self.assertEqual(marked_context.returncode, 0, marked_context.stderr)
            marked = json.loads(marked_context.stdout)
            self.assertEqual(marked["incremental"]["mode"], "incremental")
            context_document = json.loads(Path(marked["artifact_path"]).read_text(encoding="utf-8"))
            authored_notes = [
                note
                for discussion in context_document["payload"]["discussions"]
                for note in discussion["notes"]
                if note.get("author", {}).get("username") == "reviewer"
            ]
            self.assertEqual([note["body"] for note in authored_notes], [finding_body])
            environment["FAKE_DISCUSSIONS_JSON"] = published_discussions_json
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
            author_prepared = self.run_runner(
                "code-review", "prepare", "--url", target, env=environment
            )
            self.assertEqual(author_prepared.returncode, 0, author_prepared.stderr)
            author_evidence = json.loads(author_prepared.stdout)["items"][0]["artifact_path"]
            author_context = self.run_runner(
                "code-review",
                "context",
                "--evidence",
                author_evidence,
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
            blocked_report = self.run_runner(
                "code-review", "report-review", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(blocked_report.returncode, 4, blocked_report.stderr)
            blocked_payload = json.loads(blocked_report.stdout)
            self.assertEqual(blocked_payload["stage"], "stale")
            self.assertEqual(blocked_payload["next_action"]["argv"][2], "context")
            self.assertNotIn(primary_finding["summary"], blocked_payload["chat"])
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
            state.write_text("fresh", encoding="utf-8")
            source.write_text("base\nreviewed change\nfollow-up\n", encoding="utf-8")
            subprocess.run(["git", "commit", "-qam", "follow-up"], cwd=repository, check=True)
            next_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            environment["FAKE_HEAD_SHA"] = next_head
            incremental_discussions = json.loads(published_discussions_json)
            incremental_discussions[0]["notes"][0]["position"]["head_sha"] = next_head
            environment["FAKE_DISCUSSIONS_JSON"] = json.dumps(incremental_discussions)
            prepared_incremental = self.run_runner(
                "code-review", "prepare", "--url", target, env=environment
            )
            self.assertEqual(prepared_incremental.returncode, 0, prepared_incremental.stderr)
            incremental_evidence = json.loads(prepared_incremental.stdout)["items"][0][
                "artifact_path"
            ]
            incremental_context = self.run_runner(
                "code-review",
                "context",
                "--evidence",
                incremental_evidence,
                "--repo-root",
                str(repository),
                "--locale",
                "ru",
                env=environment,
            )
            self.assertEqual(incremental_context.returncode, 0, incremental_context.stderr)
            incremental_context_result = json.loads(incremental_context.stdout)
            incremental = incremental_context_result["incremental"]
            incremental_private = json.loads(
                Path(incremental_context_result["artifact_path"]).read_text(encoding="utf-8")
            )["payload"]["incremental"]
            self.assertEqual(incremental["mode"], "incremental")
            self.assertEqual(incremental["changed_paths"], ["review.txt"])
            self.assertTrue(incremental["critic_required"])
            self.assertEqual(
                [item["id"] for item in incremental_private["previous_findings"]],
                ["primary-1"],
            )
            self.assertEqual(
                [item["id"] for item in incremental_private["previous_recommended_issues"]],
                ["issue-1"],
            )
            incremental_evidence_digest = hashlib.sha256(
                Path(incremental_evidence).read_bytes()
            ).hexdigest()
            incremental_finding = {
                **primary_finding,
                "evidence": [
                    "The current retry path still calls the provider before reserving an ID."
                ],
            }
            incremental_critic_finding = {
                **critic_finding,
                "evidence": ["The changed retry path still emits no terminal signal."],
            }
            incremental_receipt = root / "incremental-receipt.json"
            incremental_receipt.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/critic-receipt/v2",
                        "external_mutations": False,
                        "evidence_digest": incremental_evidence_digest,
                        "scope_digest": incremental_private["incremental_delta_digest"],
                        "target_finding_ids": ["primary-1"],
                        "run_id": "incremental-critic-run",
                        "session_id": "incremental-critic-session",
                        "findings": [incremental_critic_finding],
                    }
                ),
                encoding="utf-8",
            )
            wrong_scope_receipt = root / "wrong-scope-receipt.json"
            wrong_scope_value = json.loads(incremental_receipt.read_text(encoding="utf-8"))
            wrong_scope_value["scope_digest"] = "0" * 64
            wrong_scope_receipt.write_text(json.dumps(wrong_scope_value), encoding="utf-8")
            rejected_scope = self.run_runner(
                "code-review",
                "record-artifact",
                "--kind",
                "critic_receipt",
                "--evidence",
                incremental_evidence,
                "--input",
                str(wrong_scope_receipt),
                env=environment,
            )
            self.assertEqual(rejected_scope.returncode, 2)
            recorded_incremental_receipt = self.run_runner(
                "code-review",
                "record-artifact",
                "--kind",
                "critic_receipt",
                "--evidence",
                incremental_evidence,
                "--input",
                str(incremental_receipt),
                env=environment,
            )
            self.assertEqual(
                recorded_incremental_receipt.returncode,
                0,
                recorded_incremental_receipt.stderr,
            )
            incremental_receipt_artifact = json.loads(recorded_incremental_receipt.stdout)[
                "artifact_path"
            ]
            incremental_receipt_digest = json.loads(recorded_incremental_receipt.stdout)["digest"]
            incremental_finalized = self.run_runner(
                "code-review", "finalize", "--artifact-root", artifact_root, env=environment
            )
            self.assertEqual(incremental_finalized.returncode, 0, incremental_finalized.stderr)
            incremental_finalize = json.loads(incremental_finalized.stdout)
            incremental_decision = root / "incremental-decision.json"
            incremental_decision.write_text(
                json.dumps(
                    {
                        "schema": "portable-gitlab/review-decision/v2",
                        "mode": "incremental",
                        "external_mutations": False,
                        "evidence_digest": incremental_evidence_digest,
                        "finalize_digest": incremental_finalize["digest"],
                        "context_digest": incremental_context_result["digest"],
                        "critic_receipt_digest": incremental_receipt_digest,
                        "verdict": "not_ready",
                        "blocking_findings": True,
                        "blocking_finding_ids": ["primary-1"],
                        "owner_decision_reasons": [],
                        "run_id": "incremental-primary-run",
                        "session_id": "incremental-primary-session",
                        "findings": [incremental_finding],
                        "unresolved_threads": [{"id": "thread:42"}],
                        "responses": [
                            {"id": "primary-1", "decision": "accept", "reason": "still active"},
                            {
                                "id": "critic-1",
                                "decision": "reject",
                                "reason": "still outside the changed contract",
                            },
                            {"id": "thread:42", "decision": "accept", "reason": "reply required"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            incremental_reviewed = self.run_runner(
                "code-review",
                "finalize-review",
                "--evidence",
                incremental_evidence,
                "--report",
                str(incremental_decision),
                "--context",
                incremental_context_result["artifact_path"],
                "--critic-receipt",
                incremental_receipt_artifact,
                "--finalize-report",
                incremental_finalize["artifact_path"],
                "--mode",
                "incremental",
                env=environment,
            )
            self.assertEqual(incremental_reviewed.returncode, 0, incremental_reviewed.stderr)
            incremental_template = self.run_runner(
                "code-review",
                "template-review",
                "--artifact-root",
                artifact_root,
                "--kind",
                "content",
                env=environment,
            )
            self.assertEqual(incremental_template.returncode, 0, incremental_template.stderr)
            incremental_threads = {
                item["id"]: item
                for item in json.loads(
                    Path(json.loads(incremental_template.stdout)["template_path"]).read_text(
                        encoding="utf-8"
                    )
                )["thread_decisions"]
            }
            incremental_content = root / "incremental-content.json"
            incremental_content.write_text(
                json.dumps(
                    {
                        "locale": "ru",
                        "chat_assessment": {
                            "necessity": {
                                "status": "supported",
                                "rationale": "Риск повторного вызова подтверждён.",
                            },
                            "relevance": {
                                "status": "current",
                                "rationale": "Проверен текущий exact head.",
                            },
                            "change": "Повторная проверка подтверждает, что риск идемпотентности сохраняется.",
                        },
                        "summary": "The follow-up keeps the original retry risk active.",
                        "architecture_assessment": "The responsibility remains with its owner.",
                        "semver_impact": "patch",
                        "semver_rationale": "No public API changes.",
                        "semver_assessment": {
                            **generated_content["semver_assessment"],
                            "policy": "No release policy was found in the fixture.",
                            "sources": ["Fixture repository and empty release catalog"],
                            "fallback_reason": "No confirmed release is available.",
                        },
                        "mr_metadata_assessment": {
                            field: {
                                "status": "ok",
                                "rationale": f"The {field} metadata remains sufficient.",
                                "recommendation": None,
                            }
                            for field in (
                                "title",
                                "description",
                                "labels",
                                "workflow_state",
                                "overall",
                            )
                        },
                        "label_assessments": [
                            {
                                "name": "next-compatible",
                                "status": "inapplicable",
                                "rationale": "Изменение имеет patch, а не minor влияние.",
                            },
                            {
                                "name": "semver::major",
                                "status": "inapplicable",
                                "rationale": "Изменение обратно совместимо.",
                            },
                            {
                                "name": "semver::patch",
                                "status": "applicable",
                                "rationale": "Исправление имеет patch влияние на SemVer.",
                            },
                            {
                                "name": "ship-ready",
                                "status": "inapplicable",
                                "rationale": "Это не публикация релиза.",
                            },
                        ],
                        "checks": ["Checked the retry delta and affected provider path."],
                        "findings": [incremental_finding],
                        "finding_publications": [
                            {
                                "finding_id": "primary-1",
                                "type": "general",
                                "path": None,
                                "line": None,
                                "old_line": None,
                                "body": "Риск повторного вызова сохраняется.",
                                "fix_mode": "patch",
                                "patch": (
                                    "diff --git a/review.txt b/review.txt\n"
                                    "--- a/review.txt\n"
                                    "+++ b/review.txt\n"
                                    "@@ -1,3 +1,4 @@\n"
                                    " base\n"
                                    " reviewed change\n"
                                    " follow-up\n"
                                    "+reserve idempotency key\n"
                                ),
                            }
                        ],
                        "previous_finding_assessments": [
                            {
                                "id": "primary-1",
                                "kind": "finding",
                                "status": "changed",
                                "previous_status": "Актуально",
                                "current_status": "Изменено",
                                "rationale": "Изменение не резервирует идентификатор операции.",
                                "action": "Обновить существующий тред.",
                                "publication_action": "reply",
                                "publication_body": "Риск повторного вызова сохраняется.",
                                "critic_required": True,
                            },
                            {
                                "id": "issue-1",
                                "kind": "issue",
                                "status": "active",
                                "previous_status": "Рекомендовано",
                                "current_status": "Рекомендовано",
                                "rationale": "Связанная подсистема не изменилась.",
                                "action": "Сохранить рекомендацию задачи.",
                                "publication_action": "no_publication",
                                "publication_body": None,
                                "critic_required": False,
                            },
                        ],
                        "issue_templates": [],
                        "recommended_issues": [
                            {
                                "id": "issue-1",
                                "title": "Track retry exhaustion observability",
                                "problem": "The broader retry subsystem lacks a terminal signal.",
                                "risk": "Operators cannot distinguish retry exhaustion.",
                                "evidence": ["The existing subsystem has no terminal metric."],
                                "reason_out_of_scope": "The subsystem is not changed by this MR.",
                                "minimum_fix": "Add the existing terminal retry metric separately.",
                                "body": "Track a terminal metric for retry exhaustion in the broader subsystem.",
                                "template_path": None,
                            }
                        ],
                        "rejected_candidates": [
                            {
                                "id": "critic-1",
                                "source": "critic",
                                "finding": incremental_critic_finding,
                                "reason": "The broader observability gap remains outside this MR.",
                                "paths": ["review.txt"],
                                "thread_ids": [],
                                "metadata_fields": [],
                                "ci": False,
                            }
                        ],
                        "rejected_candidate_assessments": [
                            {
                                "id": "critic-1",
                                "decision": "still_rejected",
                                "reason": "The delta does not move the broader gap into MR scope.",
                            }
                        ],
                        "thread_decisions": [
                            {
                                "id": "42",
                                "url": f"{target}#note_42",
                                "state": "open",
                                "assessment": "accepted",
                                "rationale": "The thread remains actionable.",
                                "outcome": "reply",
                                "proposed_response": "Тебе всё ещё нужно резервировать ключ идемпотентности до вызова.\n\n```suggestion\nreviewed change\n```",
                                "fix_mode": "suggestion",
                                "patch": None,
                                "fixing_commit": None,
                                "last_note_id": 42,
                                "last_note_body_sha256": hashlib.sha256(
                                    b"Retry needs an idempotency key"
                                ).hexdigest(),
                                "thread_sha256": incremental_threads["42"]["thread_sha256"],
                            },
                            {
                                "id": "99",
                                "url": f"{target}#note_99",
                                "state": "plain",
                                "assessment": "neutral",
                                "rationale": "The authenticated reviewer already addressed this topic.",
                                "outcome": "no_publication",
                                "proposed_response": None,
                                "fix_mode": "not_required",
                                "patch": None,
                                "fixing_commit": None,
                                "last_note_id": 99,
                                "last_note_body_sha256": hashlib.sha256(
                                    finding_body.encode()
                                ).hexdigest(),
                                "thread_sha256": incremental_threads["99"]["thread_sha256"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            incremental_plan = self.run_runner(
                "code-review",
                "scaffold-review",
                "--evidence",
                incremental_evidence,
                "--context",
                incremental_context_result["artifact_path"],
                "--decision",
                json.loads(incremental_reviewed.stdout)["artifact_path"],
                "--content",
                str(incremental_content),
                env=environment,
            )
            self.assertEqual(incremental_plan.returncode, 0, incremental_plan.stderr)
            incremental_markdown = Path(
                json.loads(incremental_plan.stdout)["markdown_path"]
            ).read_text(encoding="utf-8")
            incremental_outline = "\n".join(
                line for line in incremental_markdown.splitlines() if line.startswith(("# ", "## "))
            )
            self.assertEqual(
                incremental_outline,
                (ROOT / "tests/fixtures/code-review/incremental-plan.ru.outline")
                .read_text(encoding="utf-8")
                .strip(),
            )
            self.assertIn("Проведено инкрементальное ревью.", incremental_markdown)
            self.assertIn("Высокая", incremental_markdown)
            self.assertNotIn("`high`", incremental_markdown)
            self.assertIn("| primary-1 | Актуально | Изменено |", incremental_markdown)
            self.assertNotIn(next_head, incremental_markdown)
            retained_prepared = self.run_runner(
                "code-review",
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                "--locale",
                "ru",
                env=environment,
            )
            self.assertEqual(retained_prepared.returncode, 0, retained_prepared.stderr)
            retained_prepared_payload = json.loads(retained_prepared.stdout)
            retained_marker_context = self.run_runner(
                "code-review",
                *retained_prepared_payload["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(retained_marker_context.returncode, 0, retained_marker_context.stderr)
            retained_result = json.loads(retained_marker_context.stdout)
            self.assertEqual(retained_result["incremental"]["mode"], "unchanged")
            retained_document = json.loads(
                Path(retained_result["artifact_path"]).read_text(encoding="utf-8")
            )
            self.assertTrue(
                any(
                    note.get("author", {}).get("username") == "reviewer"
                    and "idempotency key" in note.get("body", "")
                    for discussion in retained_document["payload"]["discussions"]
                    for note in discussion["notes"]
                )
            )
            environment["FAKE_RELEASES"] = json.dumps(
                [{"tag_name": "v1.4.0", "commit": {"id": base_sha}}]
            )
            release_changed = self.run_runner(
                "code-review",
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                "--locale",
                "ru",
                env=environment,
            )
            self.assertEqual(release_changed.returncode, 0, release_changed.stderr)
            release_context = self.run_runner(
                "code-review",
                *json.loads(release_changed.stdout)["items"][0]["next_action"]["argv"][2:],
                env=environment,
            )
            self.assertEqual(release_context.returncode, 0, release_context.stderr)
            release_selection = json.loads(release_context.stdout)["incremental"]
            self.assertEqual(release_selection["mode"], "full")
            self.assertIn(
                "release evidence or target branch changed", release_selection["fallback_reasons"]
            )
            environment["FAKE_BASE_SHA"] = head_sha
            environment["FAKE_START_SHA"] = head_sha
            rebased = self.run_runner("code-review", "prepare", "--url", target, env=environment)
            self.assertEqual(rebased.returncode, 0, rebased.stderr)
            rebased_context = self.run_runner(
                "code-review",
                "context",
                "--evidence",
                json.loads(rebased.stdout)["items"][0]["artifact_path"],
                "--repo-root",
                str(repository),
                env=environment,
            )
            self.assertEqual(rebased_context.returncode, 0, rebased_context.stderr)
            fallback = json.loads(rebased_context.stdout)["incremental"]
            self.assertEqual(fallback["mode"], "full")
            self.assertIn("base_sha changed", fallback["fallback_reasons"])

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

    def test_team_artifact_write_is_direct_and_rejects_unsafe_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "artifact.txt"
            source.write_text("first", encoding="utf-8")
            environment = {"XDG_STATE_HOME": str(root / "state")}
            written = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-write",
                "--target",
                "out.txt",
                "--input",
                str(source),
                cwd=root,
                env=environment,
            )
            self.assertEqual(written.returncode, 0, written.stderr)
            payload = json.loads(written.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertEqual((root / "out.txt").read_text(encoding="utf-8"), "first")
            self.assertFalse((root / "state").exists())
            escaped = self.run_script(
                "team-sprint-start",
                "team_workflow.py",
                "artifact-write",
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
                "artifact-write",
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
