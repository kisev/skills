"""Python rewrite of the TypeScript review fixture (fake glab + synthetic repo).

The TypeScript helper writes a Node-script fake ``glab`` onto ``PATH``; the
Python port rewrites that helper as a Python script with the same recorded
request contract, so the package tests stay standard-library-only. Parity is
carried by the ported request-log tests (endpoint sequences, mutation
handling, and config state transitions mirror the TS helper exactly).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract

FAKE_GLAB = """#!/usr/bin/env python3
import json
import os
import sys

argv = sys.argv[1:]
if "api" not in argv:
    sys.stderr.write("expected glab api invocation\\n")
    raise SystemExit(1)
rest = argv[argv.index("api") + 1:]
endpoint = ""
method = "GET"
index = 0
while index < len(rest):
    item = rest[index]
    if item == "--method":
        method = rest[index + 1]
        endpoint = rest[index + 2]
        index += 3
        continue
    if item in ("--hostname", "-F", "-f"):
        index += 2
        continue
    if not item.startswith("-") and endpoint == "":
        endpoint = item
    index += 1
clean = endpoint.split("?")[0]
config_path = os.environ["FAKE_GLAB_CONFIG"]
with open(config_path, encoding="utf-8") as handle:
    config = json.load(handle)
if config.get("requests") is not None:
    with open(config["requests"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"method": method, "endpoint": clean}) + "\\n")
if method != "GET":
    if config.get("mutationError"):
        sys.stderr.write(config["mutationError"])
        raise SystemExit(1)
    payload = {}
    index = 0
    while index < len(rest):
        if rest[index] not in ("-F", "-f"):
            index += 1
            continue
        assignment = rest[index + 1]
        key, raw = assignment.split("=", 1)
        payload[key] = (
            open(raw[1:], encoding="utf-8").read()
            if raw.startswith("@")
            else raw == "true" if key == "resolved" else raw
        )
        index += 2
    if method == "POST" and clean == "projects/19/merge_requests/7/discussions/discussion-42/notes":
        config.setdefault("publishedNotes", []).append({
            "id": 43 + len(config["publishedNotes"]),
            "system": False,
            "author": {"id": 23, "username": "reviewer"},
            "body": payload["body"].rstrip(),
            "resolved": None,
            "position": None,
        })
    elif method == "PUT" and clean == "projects/19/merge_requests/7/discussions/discussion-42":
        config["resolved"] = payload.get("resolved")
    elif method == "PUT" and clean == "projects/19/merge_requests/7/discussions/returned-discussion":
        config["createdResolved"] = payload.get("resolved")
    elif method == "POST" and clean == "projects/19/merge_requests/7/discussions":
        config.setdefault("publishedNotes", []).append({
            "id": 100 + len(config["publishedNotes"]),
            "body": payload.get("body"),
        })
    elif method == "PUT" and clean == "projects/19/merge_requests/7":
        config["labels"] = [item for item in payload["labels"].split(",") if item]
    else:
        sys.stderr.write(f"unexpected mutation {method} {clean}")
        raise SystemExit(1)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    if clean.endswith("/discussions"):
        print(json.dumps({
            "id": "returned-discussion",
            "notes": [{
                "id": 100,
                "resolvable": config.get("returnedResolvable") is True,
                "resolved": False,
            }],
        }))
    else:
        print(json.dumps({}))
    raise SystemExit(0)
discussion = {
    "id": "discussion-42",
    "individual_note": False,
    "notes": [{
        "id": 42,
        "system": False,
        "resolvable": config.get("plain") is not True,
        "resolved": config.get("resolved") is True,
        "resolved_by": config.get("resolvedBy"),
        "author": {"username": config.get("rootAuthor") or "other-reviewer"},
        "body": config.get("noteBody") or "Retry needs an idempotency key",
        "position": None if config.get("plain") is True else {
            "head_sha": config.get("positionHead") or config["headSha"],
            "new_path": config["changedPath"],
            "new_line": 2,
        },
    }, *config.get("replies", []), *config.get("publishedNotes", [])],
}
value = None
if clean == "user":
    value = {"id": 23, "username": "reviewer"}
elif clean.startswith("projects/") and "%2F" in clean:
    value = {
        "id": 19,
        "path_with_namespace": clean[len("projects/"):].replace("%2F", "/"),
        "default_branch": "main",
    }
elif config.get("sourceProjectId") is not None and clean == f"projects/{config['sourceProjectId']}":
    value = {
        "id": config["sourceProjectId"],
        "path_with_namespace": config.get("sourceProjectPath") or "group/project",
        "default_branch": "main",
    }
elif clean in (
    "projects/19/repository/branches/main",
    "projects/19/releases",
    "projects/19/repository/tags",
):
    if clean.endswith("/branches/main") and config.get("targetSha"):
        value = {"commit": {"id": config["targetSha"]}}
    elif clean.endswith("/releases"):
        value = config.get("releases", [])
    elif clean.endswith("/tags"):
        value = config.get("tags", [])
    else:
        value = []
elif clean.startswith("projects/19/labels"):
    value = [
        {"name": "ship-ready", "description": "semantic-role: change_type; semantic-value: release"},
        {"name": "next-compatible", "description": "semantic-role: compatibility; semantic-value: minor"},
        {"name": "semver::major", "description": "Breaking compatibility"},
        {"name": "semver::patch", "description": "Backward-compatible fix"},
    ]
elif clean == "projects/19/merge_requests/7":
    value = {
        "iid": 7,
        "title": "Current merge request title",
        "description": "Current description",
        "sha": config["headSha"],
        "source_branch": "dev",
        "target_branch": "main",
        "web_url": "https://gitlab.example/group/project/-/merge_requests/7",
        "author": {"username": config.get("mrAuthor") or "author"},
        "state": "opened",
        "labels": config.get("labels") or [],
        "updated_at": "fresh",
        "source_project_id": config.get("sourceProjectId") or 19,
        "pipeline": config.get("mrPipeline"),
        "latest_build_started_at": config.get("latestBuildStartedAt"),
        "latest_build_finished_at": config.get("latestBuildFinishedAt"),
        "diff_refs": {
            "base_sha": config["baseSha"],
            "start_sha": config["startSha"],
            "head_sha": config["headSha"],
        },
    }
elif clean == "projects/19/merge_requests/7/changes":
    value = {
        "changes": [
            {"old_path": path, "new_path": path}
            for path in (config.get("changedPaths") or [config["changedPath"]])
        ],
        "diff_refs": {
            "base_sha": config["baseSha"],
            "start_sha": config["startSha"],
            "head_sha": config["headSha"],
        },
    }
elif clean == "projects/19/merge_requests/7/commits":
    value = [{"id": config["headSha"]}]
elif clean == "projects/19/merge_requests/7/pipelines":
    value = [{"id": 1, "sha": config["headSha"], "status": config.get("pipelineStatus") or "success"}]
elif clean in (
    "projects/19/pipelines/1/jobs",
    "projects/19/pipelines/1/bridges",
    "projects/19/merge_requests/7/notes",
):
    value = []
elif clean == "projects/19/merge_requests/7/discussions":
    value = [discussion]
if value is None:
    sys.stderr.write(f"unexpected GET {clean}\\n")
    raise SystemExit(1)
print(json.dumps(value))
"""


class ReviewFixture:
    """The prepared fixture: repository, bare origin, fake glab on PATH."""

    def __init__(self, tmp: Path, overrides: dict[str, Any] | None = None) -> None:
        self.tmp = tmp
        self.repo = tmp / "repository"
        self.repo.mkdir(parents=True)
        self.overrides = overrides or {}
        self._git(self.repo, "init", "--quiet", "--initial-branch=main")
        self._git(self.repo, "config", "commit.gpgsign", "false")
        self._git(self.repo, "config", "user.email", "reviewer@example.invalid")
        self._git(self.repo, "config", "user.name", "Example Reviewer")
        (self.repo / "review.txt").write_text("base\n")
        (self.repo / "index.txt").write_text("imports review.txt\n")
        self._git(self.repo, "add", "review.txt", "index.txt")
        self._git(self.repo, "commit", "-qm", "base")
        self.base_sha = self.head()
        (self.repo / "review.txt").write_text("base\nreviewed change\n")
        self._git(self.repo, "commit", "-qam", "change")
        self.head_sha = self.head()
        self.origin = tmp / "origin.git"
        self.origin_url = "https://gitlab.example/group/project.git"
        subprocess.run(
            ["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.origin)],
            check=True,
            capture_output=True,
        )
        self._git(self.repo, "remote", "add", "origin", self.origin_url)
        self._git(self.repo, "config", f"url.{self.origin}.insteadOf", self.origin_url)
        self._git(self.repo, "push", "-q", "origin", "main")
        self._git(self.repo, "branch", "dev", self.head_sha)
        self._git(self.repo, "push", "-q", "origin", "dev")
        subprocess.run(
            [
                "git",
                "-C",
                str(self.origin),
                "update-ref",
                "refs/merge-requests/7/head",
                self.head_sha,
            ],
            check=True,
            capture_output=True,
        )
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "glab").write_text(FAKE_GLAB)
        (bin_dir / "glab").chmod(0o755)
        self.requests_path = tmp / "requests.log"
        self.requests_path.write_text("")
        self.config: dict[str, Any] = {
            "baseSha": self.base_sha,
            "startSha": self.base_sha,
            "headSha": self.head_sha,
            "changedPath": "review.txt",
            "requests": str(self.requests_path),
            **self.overrides,
        }
        self.config_path = tmp / "glab-config.json"
        self.config_path.write_text(json.dumps(self.config))
        self._previous = {
            key: os.environ.get(key) for key in ("XDG_STATE_HOME", "PATH", "FAKE_GLAB_CONFIG")
        }
        os.environ["XDG_STATE_HOME"] = str(tmp / "state")
        os.environ["FAKE_GLAB_CONFIG"] = str(self.config_path)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        self.url = "https://gitlab.example/group/project/-/merge_requests/7"

    def close(self) -> None:
        for key, previous in self._previous.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous

    def _git(self, cwd: Path, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def head(self) -> str:
        return self._git(self.repo, "rev-parse", "HEAD")

    def git(self, *arguments: str) -> str:
        return self._git(self.repo, *arguments)

    def read_config(self) -> dict[str, Any]:
        value: dict[str, Any] = json.loads(self.config_path.read_text(encoding="utf-8"))
        return value

    def write_config(self) -> None:
        self.config_path.write_text(json.dumps(self.read_config()))

    def request_endpoints(self) -> list[str]:
        lines = [
            line
            for line in self.requests_path.read_text(encoding="utf-8").split("\n")
            if line.strip()
        ]
        return [json.loads(line)["endpoint"] for line in lines]

    def request_count(self) -> int:
        return len(self.request_endpoints())


def cast_config(path: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return value


def make_review_fixture(overrides: dict[str, Any] | None = None) -> ReviewFixture:
    tmp = Path(tempfile.mkdtemp(prefix="reviewmatic-fixture-"))
    return ReviewFixture(tmp, overrides)


def complete_draft(draft: dict[str, Any], started: dict[str, Any]) -> dict[str, Any]:
    """The completeDraft helper from the TS fixture, in Python."""
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Bound the retry write behind an idempotency key without changing callers.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path; the remark is assessed directly."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(
        str(started["draft_path"]), str(started["context_package"]["template_path"])
    )
    recorded = contract.read_json(Path(str(started["draft_path"])), "review draft")
    draft["context_package_path"] = recorded["context_package_path"]
    draft["context_package_digest"] = recorded["context_package_digest"]
    draft["question_verifications"] = []
    draft["run_id"] = "primary-run"
    draft["session_id"] = "primary-session"
    draft["critics"] = [
        {
            **started["critic_receipt_template"],
            "run_id": "critic-run",
            "session_id": "child-session",
            "findings": [],
        },
    ]
    content = cast("dict[str, Any]", draft["content"])
    content["summary"] = "The bounded change meets the agreed contract."
    content["architecture_assessment"] = "Existing ownership is preserved."
    content["chat_assessment"] = {
        "necessity": {"status": "supported", "rationale": "The existing timeout is unbounded."},
        "relevance": {"status": "current", "rationale": "The current runner uses this path."},
        "change": "Bound the check.",
    }
    content["semver_impact"] = "patch"
    content["semver_rationale"] = "Backward-compatible correction."
    content["checks"] = ["Inspected the exact committed diff; external tests were not run."]
    for value in cast("dict[str, dict[str, Any]]", content["mr_metadata_assessment"]).values():
        value["status"] = "ok"
        value["rationale"] = "The observed metadata is sufficient."
    for value in cast("list[dict[str, Any]]", content["label_assessments"]):
        value["status"] = "applicable" if value["name"] == "semver::patch" else "inapplicable"
        value["rationale"] = "Matches the assessed patch contribution."
    semver = cast("dict[str, Any]", content["semver_assessment"])
    semver["policy"] = "No publication configuration is available."
    semver["sources"] = ["Fixture repository and empty release catalog"]
    semver["fallback_reason"] = "No published release can be established."
    for thread in cast("list[dict[str, Any]]", content["thread_decisions"]):
        thread["assessment"] = "fixed"
        thread["rationale"] = "The exact reviewed code already addresses the remark."
        thread["outcome"] = (
            "no_publication"
            if thread["state"] == "resolved"
            else "reply"
            if thread["state"] == "plain"
            else "resolve"
        )
        thread["proposed_response"] = (
            None
            if thread["state"] == "resolved"
            else "The exact reviewed code now handles this path."
        )
    assert content["finding_publications"] == []
    return draft
