"""One-process review runs: drive the exact-head cycle with resume and callbacks.

The run owns every mechanical step (prepare, context, finalize, scaffold,
report) and stops only where a human or an LLM must author an artifact.  A
shell callback automates one authoring stop; without it the run prints the
ready template path and the exact manual commands, and ``--resume`` continues
from the last successful stage in a later invocation.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote as url_quote

from reviewmatic import context, workflow
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Callable

# Authoring stops: kind -> (CLI flag dest, human label).  The review decision
# arbitrates every critic finding (validate_decision), so its callback is the
# arbitrator command.
CALLBACK_DESTS: dict[str, str] = {
    "critic": "criticCmd",
    "decision": "arbitratorCmd",
    "content": "contentCmd",
}
CALLBACK_LABELS: dict[str, str] = {
    "critic": "critic receipt",
    "decision": "review decision",
    "content": "plan content",
}


def artifact_root_for_url(url: str) -> Path:
    """Derive the deterministic artifact root for one MR without collecting it."""
    target = contract.parse_target(url, {"merge_requests"})
    hostname, project_path = str(target["hostname"]), str(target["project_path"])
    project = contract.glab_json(hostname, f"projects/{url_quote(project_path, safe='')}")
    if not isinstance(project, dict) or not isinstance(project.get("id"), int):
        raise contract.WorkflowError("GitLab project identity is unavailable for this review")
    return contract.state_directory("code-review", {**target, "project_id": project["id"]})


def run_callback(command: str, template_path: Path, output: Path, label: str) -> Path:
    """Run one authoring callback; the template and output paths are $1/$2."""
    environment = {
        **os.environ,
        "REVIEWMATIC_TEMPLATE": str(template_path),
        "REVIEWMATIC_OUTPUT": str(output),
    }
    completed = subprocess.run(
        ["sh", "-c", command, "sh", str(template_path), str(output)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise contract.WorkflowError(
            f"the {label} callback failed ({completed.returncode}): "
            f"{completed.stderr.strip()[-800:]}"
        )
    if not output.is_file():
        raise contract.WorkflowError(f"the {label} callback did not write {output}")
    return output


class ReviewRun:
    """One run invocation over the exact-head review state machine."""

    def __init__(self, namespace: argparse.Namespace) -> None:
        self.url = str(getattr(namespace, "url", ""))
        self.repo_root: str | None = getattr(namespace, "repoRoot", None)
        self.mode: str = getattr(namespace, "reviewMode", None) or "normal"
        self.locale: str = getattr(namespace, "locale", None) or "en"
        self.incremental: str = getattr(namespace, "incremental", None) or "auto"
        self.resume: bool = getattr(namespace, "resume", False) is True
        self.callbacks: dict[str, str] = {
            kind: str(getattr(namespace, dest))
            for kind, dest in CALLBACK_DESTS.items()
            if getattr(namespace, dest, None)
        }
        self.root: Path | None = None
        self.stage: str | None = None
        self.timings: list[dict[str, Any]] = []
        self._started = time.monotonic()

    def log(self, message: str) -> None:
        elapsed = time.monotonic() - self._started
        print(f"[run +{elapsed:.3f}s] {message}", file=sys.stderr)

    def step(self, name: str, action: Callable[[], Any]) -> Any:
        mark = time.monotonic()
        try:
            return action()
        finally:
            seconds = round(time.monotonic() - mark, 3)
            self.timings.append({"step": name, "seconds": seconds})
            self.log(f"{name} finished in {seconds:.3f}s")

    def execute(self) -> dict[str, Any]:
        if self.resume:
            self.root = artifact_root_for_url(self.url)
            if not (self.root / context.REVIEW_EVIDENCE_NAME).exists():
                raise contract.WorkflowError(
                    f"no review state exists for {self.url}; start without --resume"
                )
            self.log(f"resuming from {self.root}")
        else:
            target = contract.parse_target(self.url, {"merge_requests"})
            bundle = cast(
                "dict[str, Any]",
                self.step(
                    "prepare",
                    lambda: contract.collect(target, "code-review", locale=self.locale),
                ),
            )
            self.root = Path(str(bundle["artifact_root"]))
            self.step(
                "begin",
                lambda: workflow.prepared(
                    argparse.Namespace(
                        repo_root=self.repo_root,
                        review_mode=self.mode,
                        locale=self.locale,
                        incremental=self.incremental,
                    ),
                    bundle,
                ),
            )
        while True:
            status = context.review_status(str(self.root))
            stage = str(status.get("resume_stage") or status.get("stage"))
            self.stage = stage
            self.log(f"stage {stage}")
            if status.get("status") == "ok" and stage == "plan_ready":
                report = cast(
                    "dict[str, Any]",
                    self.step("report", lambda: context.report_review(str(self.root))),
                )
                return self._final("ok", "plan_ready", report=report)
            if stage == "prepared":
                self._context_step(status)
                continue
            if stage == "critic_missing":
                if "critic" not in self.callbacks:
                    return self._waiting(status, "critic")
                self._callback_stage("critic")
                continue
            if stage in {"context_ready", "finalize_missing"}:
                self.step("finalize", lambda: workflow.finalize(str(self.root)))
                continue
            if stage == "decision_missing":
                if "decision" not in self.callbacks:
                    return self._waiting(status, "decision")
                self._callback_stage("decision")
                continue
            if stage == "content_missing":
                if "content" not in self.callbacks:
                    return self._waiting(status, "content")
                self._callback_stage("content")
                continue
            raise contract.WorkflowError(f"the run cannot continue from stage {stage!r}")

    def _context_step(self, status: dict[str, Any]) -> None:
        assert self.root is not None
        progress = context.load_progress(self.root) or {}
        evidence_path = progress.get("evidence_path") or status.get("evidence_path")
        repo_root = progress.get("repo_root") or self.repo_root
        if not isinstance(evidence_path, str) or not isinstance(repo_root, str):
            raise contract.WorkflowError("the context step requires --repo-root")
        self.step(
            "context",
            lambda: context.prepare_context(
                evidence_path, repo_root, self.incremental, self.mode, self.locale
            ),
        )

    def _callback_stage(self, kind: str) -> None:
        assert self.root is not None
        root = self.root
        template = cast(
            "dict[str, Any]",
            self.step(f"{kind}-template", lambda: context.template_review(str(root), kind)),
        )
        template_path = Path(str(template["template_path"]))
        output = template_path.with_name(f"{kind}-completed.json")
        self.step(
            f"{kind}-callback",
            lambda: run_callback(
                self.callbacks[kind], template_path, output, CALLBACK_LABELS[kind]
            ),
        )
        progress = context.load_progress(root) or {}
        evidence_path = str(progress.get("evidence_path") or "")
        if kind == "critic":
            self.step(
                "critic-record",
                lambda: workflow.record(
                    argparse.Namespace(
                        kind="critic_receipt", evidence=evidence_path, input=str(output)
                    )
                ),
            )
        elif kind == "decision":
            self.step(
                "decision-record",
                lambda: workflow.decide(
                    argparse.Namespace(
                        evidence=evidence_path,
                        report=str(output),
                        context=str(progress.get("context_path")),
                        finalize_report=str(progress.get("finalize_report_path")),
                        critic_receipt=progress.get("critic_receipt_path"),
                        mode=progress.get("mode"),
                    )
                ),
            )
        else:
            self.step(
                "content-scaffold",
                lambda: context.scaffold_review(
                    evidence_path,
                    str(progress.get("context_path")),
                    str(progress.get("decision_path")),
                    str(output),
                ),
            )

    def _waiting(self, status: dict[str, Any], kind: str) -> dict[str, Any]:
        assert self.root is not None
        template = context.template_review(str(self.root), kind)
        self.log(f"waiting for the {CALLBACK_LABELS[kind]} at stage {self.stage}")
        return {
            "status": "waiting",
            "stage": self.stage,
            "reason": status.get("reason"),
            "template_kind": kind,
            "template_path": template["template_path"],
            "manual_command": template["next_action"]["command"],
            "manual_argv": template["next_action"]["argv"],
            "resume_command": self.resume_command(),
            "timings": self.timings,
            "total_seconds": self._elapsed(),
            "external_mutations": False,
        }

    def _final(
        self, status: str, stage: str, report: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "status": status,
            "stage": stage,
            "artifact_root": str(self.root) if self.root else None,
            "report": report,
            "timings": self.timings,
            "total_seconds": self._elapsed(),
            "external_mutations": False,
        }

    def failure(self, error: Exception) -> dict[str, Any]:
        dump: dict[str, Any] = {
            "status": "error",
            "error": str(error),
            "url": self.url,
            "stage": self.stage,
            "artifact_root": str(self.root) if self.root else None,
            "timings": self.timings,
            "resume_command": self.resume_command(),
            "captured_at": datetime.now(UTC).isoformat(),
            "external_mutations": False,
        }
        if self.root is not None:
            with suppress(OSError, contract.WorkflowError):
                dump["progress"] = context.load_progress(self.root)
            with suppress(OSError, contract.WorkflowError):
                dump["review_status"] = context.review_status(str(self.root))
            try:
                contract.write_json(self.root / "run-failure.json", dump)
                self.log(f"state dump written to {self.root / 'run-failure.json'}")
            except OSError:
                pass
        return dump

    def resume_command(self) -> str:
        parts = ["reviewmatic", "run", "--resume", "--url", self.url]
        if self.repo_root:
            parts.extend(("--repo-root", self.repo_root))
        return " ".join(shlex.quote(value) for value in parts)

    def _elapsed(self) -> float:
        return round(time.monotonic() - self._started, 3)


def run(namespace: argparse.Namespace) -> int:
    """Execute one run invocation and return the public exit code."""
    runner = ReviewRun(namespace)
    try:
        result = runner.execute()
    except contract.WorkflowError as error:
        contract.emit(runner.failure(error))
        return 1
    contract.emit(result)
    status = str(result.get("status"))
    if status == "waiting":
        return 0
    return 0 if status == "ok" else 1
