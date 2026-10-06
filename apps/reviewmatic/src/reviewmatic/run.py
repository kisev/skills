"""One-process review runs: drive the exact-head cycle with resume and callbacks.

The run owns every mechanical step (prepare, context, finalize, scaffold,
report) and stops only where a human or an LLM must author an artifact.  A
shell callback automates one authoring stop; without it the run prints the
ready template path and the exact manual commands, and ``--resume`` continues
from the last successful stage in a later invocation.

The critic stage is a panel: ``--participants`` records the user's poll answer
(critic composition and the engine of every critic, see ``run_panel``).  OCR
critics execute mechanically inside the run without an authoring stop; model
critics stop the run for their per-critic receipt, which the ``critic``
callback authors or the agent imports with ``record-run-critic``.  A complete
panel merges into one aggregate critic receipt and the run continues.
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
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote as url_quote

from reviewmatic import context, ocr_critic, run_panel, tail, workflow
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Callable

# Authoring stops: kind -> (CLI flag dest, human label).  The "critic"
# callback authors one run-panel model critic receipt at a time; the review
# decision arbitrates every critic finding (validate_decision), so its
# callback is the arbitrator command.
CALLBACK_DESTS: dict[str, str] = {
    "critic": "criticCmd",
    "decision": "arbitratorCmd",
    "content": "contentCmd",
    "delta": "deltaCmd",
}
CALLBACK_LABELS: dict[str, str] = {
    "critic": "critic receipt",
    "decision": "review decision",
    "content": "plan content",
}

# A stage may repeat only while it makes progress: evidence collection that
# stays incomplete after this many attempts at the same stage stops the run
# loudly instead of looping forever. The state survives for --resume.
STAGE_ATTEMPT_LIMIT = 3


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
        self.repo_root: str | None = getattr(namespace, "repoRoot", None) or str(Path.cwd())
        self.mode: str = getattr(namespace, "reviewMode", None) or "normal"
        self.locale: str = getattr(namespace, "locale", None) or "en"
        self.incremental: str = getattr(namespace, "incremental", None) or "auto"
        self.participants: str | None = getattr(namespace, "participants", None)
        self.ocr_provider: str | None = getattr(namespace, "ocrProvider", None)
        self.ocr_model: str | None = getattr(namespace, "ocrModel", None)
        self.resume: bool = getattr(namespace, "resume", False) is True
        self.callbacks: dict[str, str] = {
            kind: str(getattr(namespace, dest))
            for kind, dest in CALLBACK_DESTS.items()
            if getattr(namespace, dest, None)
        }
        self.root: Path | None = None
        self.stage: str | None = None
        self.timings: list[dict[str, Any]] = []
        self.incomplete_evidence: list[str] = []
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
        if self.participants is not None and self.mode == "fast":
            raise contract.WorkflowError(
                "the run panel applies to normal, deep, and incremental reviews; a fast review "
                "runs without critics, so --participants has no stage to apply to"
            )
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
        attempts = 0
        previous_progress: tuple[object, ...] | None = None
        while True:
            authoring = tail.load(self.root)
            if authoring and authoring.get("pending_delta"):
                if self.participants is not None:
                    raise contract.WorkflowError(
                        "--participants cannot replace a delta continuation; omit it to keep the selected verifier and historical panel"
                    )
                if "delta" in self.callbacks:
                    template_path = Path(authoring["pending_delta"]["template_path"])
                    output_path = template_path.with_name("delta-completed.json")
                    self.step(
                        "delta-callback",
                        partial(
                            run_callback,
                            self.callbacks["delta"],
                            template_path,
                            output_path,
                            "delta verification",
                        ),
                    )
                    checked = self.step(
                        "delta-record", partial(tail.record_delta, self.root, str(output_path))
                    )
                    if checked["status"] == "ok":
                        continue
                return self._waiting_delta(authoring)
            status = context.review_status(str(self.root))
            stage = str(status.get("resume_stage") or status.get("stage"))
            self.stage = stage
            self.log(f"stage {stage}")
            observed = context.load_progress(self.root) or {}
            token = (
                stage,
                *(
                    observed.get(f"{key}_digest")
                    for key in ("evidence", "context", "critic_receipt", "decision")
                ),
            )
            if token == previous_progress:
                attempts += 1
            else:
                attempts = 1
                previous_progress = token
            if attempts > STAGE_ATTEMPT_LIMIT:
                raise contract.WorkflowError(
                    f"evidence stays incomplete after {STAGE_ATTEMPT_LIMIT} attempts: "
                    + "; ".join(self.incomplete_evidence or [str(status.get("reason"))])
                )
            if status.get("status") == "ok" and stage == "plan_ready":
                assert self.root is not None
                if self.participants is not None and run_panel.load(self.root) is None:
                    raise contract.WorkflowError(
                        "participants were provided but the review selected the unchanged mode "
                        "without a panel; the poll answer was never used"
                    )
                report = cast(
                    "dict[str, Any]",
                    self.step("report", lambda: context.report_review(str(self.root))),
                )
                return self._final("ok", "plan_ready", report=report)
            if stage == "prepared":
                self._context_step(status)
                continue
            if stage == "critic_missing":
                assert self.root is not None
                panel = run_panel.load(self.root)
                if panel is None:
                    if self.participants is None:
                        return self._waiting_participants(status)
                    self.step("panel-selection", self._panel_selection)
                    self.participants = None
                    continue
                if self.participants is not None:
                    bound = [
                        str(critic["name"])
                        for critic in run_panel.selected_critics(panel)
                        if isinstance(critic.get("receipt"), dict)
                    ]
                    if bound:
                        raise contract.WorkflowError(
                            "--participants cannot replace the recorded panel: bound critic "
                            f"receipts exist for {', '.join(bound)}. Omit --participants to "
                            "continue the recorded panel, or start a fresh reviewmatic run "
                            "without --resume to ask the poll again"
                        )
                    self.step("panel-selection", self._panel_selection)
                    self.participants = None
                    continue
                waiting = self._panel_step(panel, status)
                if waiting is not None:
                    return waiting
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
                changed = self.step(
                    "delta-preflight", lambda: tail.re_anchor(cast("Path", self.root))
                )
                if changed is not None:
                    continue
                state = self.step("content-render", lambda: tail.prepare(cast("Path", self.root)))
                if state.get("applied"):
                    self.step("content-finalize", lambda: tail.finalize(cast("Path", self.root)))
                    continue
                if "content" not in self.callbacks:
                    return self._waiting_prose(status, state)
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
        result = cast(
            "dict[str, Any]",
            self.step(
                "context",
                lambda: context.prepare_context(
                    evidence_path, repo_root, self.incremental, self.mode, self.locale
                ),
            ),
        )
        if result.get("status") == "incomplete":
            summary = cast("dict[str, Any]", result.get("summary") or {})
            self.incomplete_evidence = [
                str(item) for item in cast("list[object]", summary.get("risks") or [])
            ]

    def _callback_stage(self, kind: str) -> None:
        assert self.root is not None
        root = self.root
        template = (
            {"template_path": tail.prepare(root)["prose_path"]}
            if kind == "content"
            else cast(
                "dict[str, Any]",
                self.step(f"{kind}-template", lambda: context.template_review(str(root), kind)),
            )
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
        if kind == "decision":
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
        elif kind == "content":
            self.step(
                "content-prose-apply",
                lambda: tail.record_prose(root, str(output)),
            )
        else:
            raise contract.WorkflowError(f"unknown authoring callback kind {kind!r}")

    def _panel_selection(self) -> dict[str, Any]:
        """Record the poll answer passed with --participants (validation is loud)."""
        assert self.root is not None
        progress = context.load_progress(self.root) or {}
        return run_panel.record_selection(
            self.root,
            str(self.participants),
            self.ocr_provider,
            self.ocr_model,
            str(progress.get("mode") or self.mode),
        )

    def _panel_step(self, panel: dict[str, Any], status: dict[str, Any]) -> dict[str, Any] | None:
        """Execute pending OCR critics mechanically, stop for model critics."""
        assert self.root is not None
        root = self.root
        progress = context.load_progress(root) or {}
        context_artifact = context.progress_artifact(root, progress, "context", "review_context")
        if context_artifact is None:
            raise contract.WorkflowError("the run panel requires the selected review context")
        review_context = context_artifact[1]
        context_digest = str(progress["context_digest"])
        scope = (
            cast("dict[str, Any]", review_context["incremental"])["incremental_delta_digest"]
            if progress.get("mode") == "incremental"
            else None
        )
        _, evidence = context.review_evidence_from_root(root)
        for critic in run_panel.pending_critics(panel):
            if ocr_critic.critic_engine(critic) == "ocr":
                participant = str(critic["name"])
                self.log(f"executing the OCR critic {participant} mechanically")
                panel = self.step(
                    f"ocr-critic-{participant}",
                    partial(
                        run_panel.run_ocr_critic,
                        root,
                        progress,
                        review_context,
                        context_digest,
                        evidence,
                        critic,
                        scope,
                    ),
                )
        model_pending = [
            critic
            for critic in run_panel.pending_critics(panel)
            if ocr_critic.critic_engine(critic) == "model"
        ]
        if not model_pending:
            self.step("critic-merge", lambda: workflow.complete_run_panel(str(root)))
            return None
        if "critic" in self.callbacks:
            for critic in model_pending:
                participant = str(critic["name"])
                template_path = run_panel.critic_template(
                    root, review_context, str(progress["mode"]), context_digest, participant
                )
                output = template_path.with_name(
                    f"critic-{ocr_critic.safe_id_fragment(participant)}-completed.json"
                )
                self.step(
                    f"critic-callback-{participant}",
                    partial(
                        run_callback,
                        self.callbacks["critic"],
                        template_path,
                        output,
                        f"critic receipt for {participant}",
                    ),
                )
                self.step(
                    f"critic-record-{participant}",
                    partial(
                        workflow.record_run_critic,
                        argparse.Namespace(
                            artifact_root=str(root),
                            input=str(output),
                            participant=str(critic["name"]),
                        ),
                    ),
                )
            # The last record_run_critic completes the panel itself; a pure-OCR
            # panel merges through the critic-merge step above.
            return None
        return self._waiting_panel(panel, status)

    def _waiting_participants(self, status: dict[str, Any]) -> dict[str, Any]:
        """Stop at the one poll: critic composition and the engine of every critic."""
        assert self.root is not None
        root = self.root
        progress = context.load_progress(root) or {}
        locale = str(progress.get("locale") or self.locale)
        mode = str(progress.get("mode") or self.mode)
        context_digest = str(progress.get("context_digest") or "")
        context_artifact = context.progress_artifact(root, progress, "context", "review_context")
        if context_artifact is None:
            raise contract.WorkflowError("the panel poll requires the selected review context")
        background, background_bytes = run_panel.render_run_background(
            root, context_artifact[1], context_digest
        )
        poll = run_panel.poll(locale, mode, background_bytes)
        template_path = run_panel.selection_template(root, context_digest)
        argv = [
            "reviewmatic",
            "run",
            "--resume",
            "--url",
            self.url,
            "--participants",
            str(template_path),
        ]
        if self.repo_root:
            argv.extend(("--repo-root", self.repo_root))
        self.log("waiting for the panel selection at stage critic_missing")
        return {
            "status": "waiting",
            "stage": self.stage,
            "reason": status.get("reason"),
            "artifact_root": str(root),
            "template_kind": "participants",
            "template_path": str(template_path),
            "poll": poll,
            "background_path": str(background),
            "rules": run_panel.poll_rules(locale),
            "manual_command": " ".join(shlex.quote(value) for value in argv),
            "manual_argv": argv,
            "resume_command": self.resume_command(),
            "timings": self.timings,
            "total_seconds": self._elapsed(),
            "external_mutations": False,
        }

    def _waiting_panel(self, panel: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
        """Stop for the first pending model critic with its ready template."""
        assert self.root is not None
        root = self.root
        progress = context.load_progress(root) or {}
        context_artifact = context.progress_artifact(root, progress, "context", "review_context")
        if context_artifact is None:
            raise contract.WorkflowError("the run panel requires the selected review context")
        pending = run_panel.pending_critics(panel)
        participant = str(pending[0]["name"])
        template_path = run_panel.critic_template(
            root,
            context_artifact[1],
            str(progress["mode"]),
            str(progress["context_digest"]),
            participant,
        )
        action = context.runner_action(
            "record-run-critic",
            "--artifact-root",
            str(root),
            "--input",
            str(template_path),
            "--participant",
            participant,
        )
        self.log(f"waiting for the critic receipt of {participant} at stage {self.stage}")
        return {
            "status": "waiting",
            "stage": self.stage,
            "reason": status.get("reason"),
            "artifact_root": str(root),
            "template_kind": "critic",
            "participant": participant,
            "panel": run_panel.summary(panel),
            "template_path": str(template_path),
            "manual_command": action["command"],
            "manual_argv": action["argv"],
            "resume_command": self.resume_command(),
            "timings": self.timings,
            "total_seconds": self._elapsed(),
            "external_mutations": False,
        }

    def _waiting(self, status: dict[str, Any], kind: str) -> dict[str, Any]:
        assert self.root is not None
        template = context.template_review(str(self.root), kind)
        self.log(f"waiting for the {CALLBACK_LABELS[kind]} at stage {self.stage}")
        panel = run_panel.load(self.root)
        return {
            "status": "waiting",
            "stage": self.stage,
            "reason": status.get("reason"),
            "artifact_root": str(self.root),
            "template_kind": kind,
            "template_path": template["template_path"],
            **({"panel": run_panel.summary(panel)} if panel is not None else {}),
            "manual_command": template["next_action"]["command"],
            "manual_argv": template["next_action"]["argv"],
            "resume_command": self.resume_command(),
            "timings": self.timings,
            "total_seconds": self._elapsed(),
            "external_mutations": False,
        }

    def _waiting_prose(self, status: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        assert self.root is not None
        action = context.runner_action(
            "record-prose", "--artifact-root", str(self.root), "--input", str(state["prose_path"])
        )
        return {
            "status": "waiting",
            "stage": "content_missing",
            "template_kind": "prose",
            "artifact_root": str(self.root),
            "reason": status.get("reason"),
            "template_path": state["prose_path"],
            "manual_command": action["command"],
            "manual_argv": action["argv"],
            "resume_command": self.resume_command(),
            "timings": self.timings,
            "total_seconds": self._elapsed(),
            "external_mutations": False,
            "clarification": state.get("clarification"),
        }

    def _waiting_delta(self, state: dict[str, Any]) -> dict[str, Any]:
        assert self.root is not None
        pending = state["pending_delta"]
        action = context.runner_action(
            "record-delta",
            "--artifact-root",
            str(self.root),
            "--input",
            str(pending["template_path"]),
        )
        panel = run_panel.load(self.root)
        return {
            "status": "waiting",
            "stage": "delta_check_missing",
            "template_kind": "delta",
            "artifact_root": str(self.root),
            "template_path": pending["template_path"],
            "history_path": pending["history_path"],
            "scope": pending["scope"],
            "targets": pending["targets"],
            "inputs": {
                key: (context.load_progress(self.root) or {}).get(key)
                for key in ("evidence_path", "context_path", "repo_root")
            },
            "verifier": panel.get("participants", {}).get("arbitrator") if panel else None,
            "rules": "Use a fresh independent native session for the selected verifier. Check the new delta and affected conclusions using dependencies and related consumers. Line mapping proves a position, never truth. Confirm, refute, revise, or leave not_verified explicitly; inspect new defects too. Historical receipts remain bound to their original snapshot. Address only affected conclusions; preserve authored prose.",
            "affected": pending.get("needs_addressed", []),
            "prose_path": state["prose_path"],
            "manual_command": action["command"],
            "manual_argv": action["argv"],
            "resume_command": self.resume_command(),
            "timings": self.timings,
            "total_seconds": self._elapsed(),
            "external_mutations": False,
        }

    def _final(
        self, status: str, stage: str, report: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        panel = run_panel.load(self.root) if self.root is not None else None
        authored = tail.load(self.root) if self.root is not None else None
        return {
            "status": status,
            "stage": stage,
            "artifact_root": str(self.root) if self.root else None,
            "report": report,
            **({"panel": run_panel.summary(panel)} if panel is not None else {}),
            **(
                {
                    "panel_role": "historical",
                    "delta_checks": authored["delta_checks"],
                    "authorship_history": authored.get("history", []),
                }
                if authored and authored.get("delta_checks")
                else {}
            ),
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
