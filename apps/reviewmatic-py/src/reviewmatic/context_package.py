"""Context packages: canonical digests, question bindings, and templates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reviewmatic import context
from reviewmatic.portable.portable_gitlab import contract

PACKAGE_POINTER_NAME = "context-package.json"
ZERO_DIGEST = "0" * 64
VERDICTS = {"confirmed", "refuted", "not_verified"}
PRIMARY_VERDICTS = {"confirmed", "refuted", "unresolved"}
CANONICAL_FIELDS = (
    "mode",
    "binding",
    "goal",
    "acceptance_criteria",
    "claims",
    "constraints",
    "prior_decisions",
    "questions",
    "thread_registry",
    "supersedes",
)


def _artifact_envelope(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"portable-gitlab/{kind}/v2",
        "schema_version": contract.ARTIFACT_VERSION,
        "kind": kind,
        "created_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }


# The narrative background is intentionally excluded: editing it must never
# change the canonical facts of a recorded package.
def canonical_package_digest(payload: dict[str, Any]) -> str:
    value = {key: payload.get(key) for key in CANONICAL_FIELDS}
    return contract.digest(value)


def narrative_package_digest(payload: dict[str, Any]) -> str:
    return contract.digest(payload.get("background") or "")


def _shared_context_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal": payload.get("goal"),
        "acceptance_criteria": payload.get("acceptance_criteria"),
        "claims": payload.get("claims", []),
        "constraints": payload.get("constraints", []),
        "prior_decisions": payload.get("prior_decisions", []),
        "thread_registry": payload.get("thread_registry"),
    }


def question_context_digest(payload: dict[str, Any]) -> str:
    return contract.digest(
        {**_shared_context_inputs(payload), "questions": payload.get("questions", [])}
    )


def question_context_version(payload: dict[str, Any], question: dict[str, Any]) -> str:
    content = {key: value for key, value in question.items() if key != "context_digest"}
    return contract.digest({**_shared_context_inputs(payload), "question": content})


def question_context_versions(payload: dict[str, Any]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for question in payload.get("questions") or []:
        versions[str(question["id"])] = question_context_version(payload, question)
    return versions


def question_context_version_list(payload: dict[str, Any]) -> dict[str, str]:
    return question_context_versions(payload)


def bind_question_contexts(payload: dict[str, Any]) -> None:
    for question in payload.get("questions") or []:
        expected = question_context_version(payload, question)
        if "context_digest" in question and question["context_digest"] != expected:
            raise contract.WorkflowError(
                f"context package question {question['id']} context_digest does not match its "
                "meaningful context; remove manual bindings and let record-package stamp them"
            )
        question["context_digest"] = expected


def _verify_question_contexts(payload: dict[str, Any]) -> None:
    versions = question_context_versions(payload)
    for question in payload.get("questions") or []:
        if "context_digest" not in question:
            continue
        expected = versions[str(question["id"])]
        if question["context_digest"] != expected:
            raise contract.WorkflowError(
                f"context package question {question['id']} context_digest does not match its "
                f"meaningful context ({expected}); re-record the package instead of editing "
                "bindings"
            )


def _require_current_binding(
    item: dict[str, Any], versions: dict[str, str], description: str
) -> None:
    question_id = str(item["question_id"])
    stored = item.get("context_digest")
    expected = versions.get(question_id)
    if not isinstance(stored, str) or len(stored) == 0:
        raise contract.WorkflowError(
            f"{description} for question {question_id} has no context binding; every result "
            "must copy the question context_digest of the recorded context package it was "
            "produced against, so a result for older wording can never certify the current "
            "question"
        )
    if stored != expected:
        raise contract.WorkflowError(
            f"{description} for question {question_id} is bound to context digest {stored}, "
            f"but the recorded package's meaningful context for this question is {expected}; "
            "collect a fresh result bound to the current package and keep this one as "
            "superseded history"
        )


@dataclass
class SupersededResults:
    entry: dict[str, Any]
    question_ids: list[str]
    answers: list[dict[str, Any]]
    verifications: list[dict[str, Any]]


def is_current_result(item: dict[str, Any], versions: dict[str, str]) -> bool:
    return item.get("context_digest") == versions.get(str(item["question_id"]))


def extract_superseded_results(
    previous: dict[str, Any] | None,
    next_payload: dict[str, Any],
    answers: list[dict[str, Any]],
    verifications: list[dict[str, Any]],
) -> SupersededResults | None:
    versions = question_context_versions(next_payload)

    def stale(item: dict[str, Any]) -> bool:
        return not is_current_result(item, versions)

    stale_answers = [item for item in answers if stale(item)]
    stale_verifications = [item for item in verifications if stale(item)]
    if not stale_answers and not stale_verifications:
        return None
    return SupersededResults(
        entry={
            "context_digest": (
                ZERO_DIGEST if previous is None else question_context_digest(previous["payload"])
            ),
            "package_digest": ZERO_DIGEST if previous is None else previous["digest"],
            "answers": stale_answers,
            "verifications": stale_verifications,
        },
        question_ids=list(
            dict.fromkeys(
                str(item["question_id"]) for item in [*stale_answers, *stale_verifications]
            )
        ),
        answers=stale_answers,
        verifications=stale_verifications,
    )


def package_pointer_path(root: str | Path) -> Path:
    return Path(root) / PACKAGE_POINTER_NAME


def read_package_pointer(root: str | Path) -> dict[str, Any] | None:
    path = package_pointer_path(root)
    if not path.exists():
        return None
    return contract.read_json(
        contract.regular_file(path, "context package pointer"), "context package pointer"
    )


def recorded_package(root: str | Path) -> dict[str, Any] | None:
    pointer = read_package_pointer(root)
    if pointer is None:
        return None
    _, payload = contract.artifact_payload(Path(str(pointer["package_path"])), "context_package")
    return {
        "path": str(pointer["package_path"]),
        "digest": str(pointer["package_digest"]),
        "payload": payload,
    }


def thread_registry_from_context(context_value: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = context.expected_thread_bindings(context_value)
    return [
        {
            "id": thread_id,
            "url": str(binding.get("url") or ""),
            "state": str(binding["state"]),
            "summary": "",
            "review_relevance": "",
        }
        for thread_id, binding in bindings.items()
    ]


def local_section_digests(bundle: dict[str, Any]) -> dict[str, Any]:
    sections = bundle["sections"]
    return {
        "committed": str(sections["committed"]["sha256"]),
        "staged": str(sections["staged"]["sha256"]),
        "unstaged": str(sections["unstaged"]["sha256"]),
        "untracked": contract.digest(sections["untracked"]),
    }


def _previous_decisions_from_local_report(previous: dict[str, Any]) -> list[dict[str, Any]]:
    task = previous["task"]
    source = f"previous finalized local report {previous['evidence_digest']}"
    decisions: list[dict[str, Any]] = []
    for index, item in enumerate(task.get("accepted_risks") or [], start=1):
        decisions.append({"id": f"prior-risk-{index}", "decision": str(item), "source": source})
    for index, item in enumerate(task.get("deferred") or [], start=1):
        decisions.append({"id": f"prior-deferred-{index}", "decision": str(item), "source": source})
    return decisions


def _previous_decisions_from_context(context_value: dict[str, Any]) -> list[dict[str, Any]]:
    incremental = context_value.get("incremental")
    if not isinstance(incremental, dict):
        return []
    baseline = incremental.get("incremental_baseline")
    plan_digest = baseline.get("plan_digest") if isinstance(baseline, dict) else None
    source = f"previous finalized plan {plan_digest if plan_digest is not None else ''}"
    return [
        {
            "id": f"prior-thread-{_safe_id(item['id'])}",
            "decision": f"{item['outcome']}: {item['rationale']}",
            "source": str(item.get("url") if item.get("url") is not None else source),
        }
        for item in incremental.get("previous_thread_decisions") or []
    ]


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(value))[:48]


def package_template_for_mr(
    evidence: dict[str, Any], context_value: dict[str, Any]
) -> dict[str, Any]:
    exact = context_value["exact_git"]
    return {
        "schema": "portable-gitlab/context-package/v2",
        "mode": "mr",
        "binding": {
            "evidence_digest": "",
            "artifact_root": str(evidence["artifact_root"]),
            "repo_root": str(exact["repo_root"]),
            "base_sha": str(evidence["base_sha"]),
            "start_sha": str(evidence["start_sha"]),
            "head_sha": str(evidence["head_sha"]),
            "target_sha": None
            if evidence.get("target_sha") is None
            else str(evidence["target_sha"]),
            "target_ref": None
            if evidence.get("target_ref") is None
            else str(evidence["target_ref"]),
        },
        "goal": {"status": "unknown"},
        "acceptance_criteria": {"status": "unknown", "items": []},
        "background": "",
        "claims": [],
        "constraints": [],
        "prior_decisions": _previous_decisions_from_context(context_value),
        "questions": [],
        "thread_registry": thread_registry_from_context(context_value),
        "supersedes": None,
        "external_mutations": False,
    }


def package_template_for_local(
    bundle: dict[str, Any], digest_value: str, previous: dict[str, Any] | None
) -> dict[str, Any]:
    task = None if previous is None else previous["task"]
    goal: dict[str, Any] = {"status": "unknown"}
    if task is not None:
        text = str(task.get("goal") if task.get("goal") is not None else "")
        if text:
            goal = {"status": "unknown", "text": text}
    return {
        "schema": "portable-gitlab/context-package/v2",
        "mode": "local",
        "binding": {
            "evidence_digest": digest_value,
            "artifact_root": str(bundle["artifact_root"]),
            "repo_root": str(bundle["repo_root"]),
            "base_sha": str(bundle["base_sha"]),
            "head_sha": str(bundle["head_sha"]),
            "ref": None if bundle.get("ref") is None else str(bundle["ref"]),
            "sections": local_section_digests(bundle),
        },
        "goal": goal,
        "acceptance_criteria": {
            "status": "unknown",
            "items": list((task or {}).get("acceptance_criteria") or []),
        },
        "background": "",
        "claims": [],
        "constraints": list((task or {}).get("constraints") or []),
        "prior_decisions": []
        if previous is None
        else _previous_decisions_from_local_report(previous),
        "questions": [],
        "supersedes": None,
        "external_mutations": False,
    }


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or value == "":
        raise contract.WorkflowError(f"context package {field_name} must be a non-empty string")


def validate_answers(
    answers: object,
    question_ids: set[str],
    versions: dict[str, str],
    field_name: str,
) -> list[dict[str, Any]]:
    if not isinstance(answers, list):
        raise contract.WorkflowError(f"{field_name} must be an array")
    seen: set[str] = set()
    for index, item in enumerate(answers):
        answer: dict[str, Any] = item if isinstance(item, dict) else {}
        where = f"{field_name}[{index}]"
        if not isinstance(item, dict):
            raise contract.WorkflowError(f"{where} must be an object")
        _require_text(answer.get("question_id"), f"{where}.question_id")
        if str(answer["question_id"]) not in question_ids:
            raise contract.WorkflowError(
                f"{where}.question_id does not name a question of the recorded context package"
            )
        if str(answer.get("verdict")) not in VERDICTS:
            raise contract.WorkflowError(
                f"{where}.verdict must be confirmed, refuted, or not_verified"
            )
        if (
            len(str(answer.get("evidence") or "")) == 0
            and len(str(answer.get("reason") or "")) == 0
        ):
            raise contract.WorkflowError(
                f"{where} requires evidence for confirmed/refuted or a concrete reason for "
                "not_verified"
            )
        _require_text(answer.get("run_id"), f"{where}.run_id")
        _require_text(answer.get("session_id"), f"{where}.session_id")
        _require_current_binding(answer, versions, where)
        key = f"{answer['run_id']}:{answer['session_id']}:{answer['question_id']}"
        if key in seen:
            raise contract.WorkflowError(f"{where} duplicates one answer for the same critic")
        seen.add(key)
    return answers


def validate_verifications(
    verifications: object,
    question_ids: set[str],
    versions: dict[str, str],
    answers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(verifications, list):
        raise contract.WorkflowError("verifications must be an array")

    def answer_key(answer: dict[str, Any]) -> str:
        return (
            f"{answer.get('run_id') or ''}:{answer.get('session_id') or ''}:"
            f"{answer['question_id']}:{answer['verdict']}"
        )

    available = {answer_key(answer): answer for answer in answers}
    covered: set[str] = set()
    for index, item in enumerate(verifications):
        verification: dict[str, Any] = item if isinstance(item, dict) else {}
        where = f"question_verifications[{index}]"
        if not isinstance(item, dict):
            raise contract.WorkflowError(f"{where} must be an object")
        _require_text(verification.get("question_id"), f"{where}.question_id")
        if str(verification["question_id"]) not in question_ids:
            raise contract.WorkflowError(
                f"{where}.question_id does not name a question of the recorded context package"
            )
        _require_current_binding(verification, versions, where)
        original = verification.get("original")
        if (
            not isinstance(original, dict)
            or not isinstance(original.get("run_id"), str)
            or original["run_id"] == ""
            or not isinstance(original.get("session_id"), str)
            or original["session_id"] == ""
            or str(original.get("verdict")) not in VERDICTS
        ):
            raise contract.WorkflowError(
                f"{where}.original must name the preserved critic answer run, session, and verdict"
            )
        if str(verification.get("verdict")) not in PRIMARY_VERDICTS:
            raise contract.WorkflowError(
                f"{where}.verdict must be confirmed, refuted, or unresolved"
            )
        if (
            len(str(verification.get("evidence") or "")) == 0
            and len(str(verification.get("reason") or "")) == 0
        ):
            raise contract.WorkflowError(
                f"{where} requires evidence or an explicit reason; insufficient evidence "
                "stays visible"
            )
        key = answer_key(
            {
                "run_id": original["run_id"],
                "session_id": original["session_id"],
                "question_id": verification["question_id"],
                "verdict": original["verdict"],
            }
        )
        answered = any(
            str(answer.get("question_id")) == str(verification["question_id"]) for answer in answers
        )
        if key not in available and answered:
            raise contract.WorkflowError(
                f"{where}.original does not match any retained critic answer; keep the "
                "original answer separately"
            )
        dedupe = f"{original['run_id']}:{original['session_id']}:{verification['question_id']}"
        if dedupe in covered:
            raise contract.WorkflowError(f"{where} verifies the same critic answer twice")
        covered.add(dedupe)
    return verifications


def collect_answers(
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    answers: list[dict[str, Any]] = []
    for source in sources:
        for answer in source.get("question_answers") or []:
            merged = {
                **answer,
                "run_id": (
                    answer["run_id"] if answer.get("run_id") is not None else source.get("run_id")
                ),
                "session_id": (
                    answer["session_id"]
                    if answer.get("session_id") is not None
                    else source.get("session_id")
                ),
            }
            answers.append(merged)
    by_question: dict[str, list[dict[str, Any]]] = {}
    for answer in answers:
        by_question.setdefault(str(answer["question_id"]), []).append(answer)
    contradictions = [
        question_id
        for question_id, items in by_question.items()
        if {str(item["verdict"]) for item in items} >= {"confirmed", "refuted"}
    ]
    return answers, contradictions


def question_report(
    questions: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    verifications: list[dict[str, Any]],
) -> dict[str, Any]:
    assigned = [item for item in questions if item.get("critic") is True]
    assigned_ids = {str(item["id"]) for item in assigned}
    answered = {str(answer["question_id"]) for answer in answers}

    def answer_key(answer: dict[str, Any]) -> str:
        return (
            f"{answer.get('run_id') or ''}:{answer.get('session_id') or ''}:{answer['question_id']}"
        )

    not_verified = {
        answer_key(answer) for answer in answers if answer.get("verdict") == "not_verified"
    }
    verified = {
        str(item["question_id"]) for item in verifications if item.get("verdict") != "unresolved"
    }
    # A not_verified critic answer stops counting as unverified exactly when a
    # primary verification preserved that original answer; a verification of a
    # different original never rescues it.
    resolved = {
        f"{(item['original'] or {}).get('run_id') or ''}:"
        f"{(item['original'] or {}).get('session_id') or ''}:{item['question_id']}"
        for item in verifications
        if item.get("verdict") != "unresolved" and isinstance(item.get("original"), dict)
    }
    unresolved = {
        str(item["question_id"]) for item in verifications if item.get("verdict") == "unresolved"
    }
    by_question: dict[str, set[str]] = {}
    for answer in answers:
        by_question.setdefault(str(answer["question_id"]), set()).add(str(answer["verdict"]))
    contradicted = sum(
        1 for verdicts in by_question.values() if "confirmed" in verdicts and "refuted" in verdicts
    )
    return {
        "assigned": len(assigned),
        "answered": len([item for item in answered if item in assigned_ids]),
        "unverified": len([item for item in not_verified if item not in resolved]),
        "verified": len(verified),
        "unresolved": len(unresolved),
        "contradicted": contradicted,
    }


def stale_thread_ids(
    previous_registry: list[dict[str, Any]],
    previous_bindings: dict[str, dict[str, Any]],
    current_bindings: dict[str, dict[str, Any]],
) -> list[str]:
    keys = ("state", "url", "last_note_id", "last_note_body_sha256", "thread_sha256")
    return [
        str(item["id"])
        for item in previous_registry
        if _thread_binding_changed(str(item["id"]), previous_bindings, current_bindings, keys)
    ]


def _thread_binding_changed(
    thread_id: str,
    previous_bindings: dict[str, dict[str, Any]],
    current_bindings: dict[str, dict[str, Any]],
    keys: tuple[str, ...],
) -> bool:
    binding = previous_bindings.get(thread_id)
    current = current_bindings.get(thread_id)
    if binding is None or current is None:
        return True
    return any(
        contract.digest(binding.get(key)) != contract.digest(current.get(key)) for key in keys
    )


@dataclass
class ExpectedPackage:
    mode: str
    evidence_digest: str
    artifact_root: str
    repo_root: str
    base_sha: str | None = None
    start_sha: str | None = None
    head_sha: str | None = None
    target_sha: str | None = None
    target_ref: str | None = None
    ref: str | None = None
    sections: dict[str, Any] | None = None
    bindings: dict[str, dict[str, Any]] = field(default_factory=dict)


def _require_goal_text(goal: dict[str, Any]) -> bool:
    return isinstance(goal.get("text"), str) and goal["text"] != ""


def validate_package_payload(payload: dict[str, Any], expected: ExpectedPackage) -> None:
    contract.validate_v2_artifact(_artifact_envelope("context_package", payload), "context_package")
    if payload["mode"] != expected.mode:
        raise contract.WorkflowError("context package mode must match the selected review target")
    binding = payload["binding"]
    if binding["evidence_digest"] != expected.evidence_digest:
        raise contract.WorkflowError("context package does not bind the selected evidence digest")
    if binding["artifact_root"] != expected.artifact_root:
        raise contract.WorkflowError("context package does not bind this review artifact root")
    if binding["repo_root"] != expected.repo_root:
        raise contract.WorkflowError(
            "context package repo_root does not match the selected checkout"
        )
    if expected.mode == "mr":
        for key, value in (
            ("base_sha", expected.base_sha),
            ("start_sha", expected.start_sha),
            ("head_sha", expected.head_sha),
        ):
            if binding[key] != value:
                raise contract.WorkflowError(
                    f"context package {key} must match the exact reviewed revision"
                )
        if expected.target_sha is not None and binding.get("target_sha") != expected.target_sha:
            raise contract.WorkflowError(
                "context package target_sha must match the exact target revision"
            )
        if "sections" in binding:
            raise contract.WorkflowError(
                "context package binding must not claim local sections in MR mode"
            )
        registry = payload["thread_registry"]
        expected_ids = set(expected.bindings.keys())
        seen: set[str] = set()
        for item in registry:
            thread_id = str(item["id"])
            if thread_id not in expected_ids:
                raise contract.WorkflowError(
                    f"context package thread {thread_id} is not part of the collected evidence"
                )
            if thread_id in seen:
                raise contract.WorkflowError(
                    f"context package thread registry repeats thread {thread_id}"
                )
            seen.add(thread_id)
            _require_text(item.get("summary"), f"thread_registry summary for {thread_id}")
            _require_text(
                item.get("review_relevance"), f"thread_registry review_relevance for {thread_id}"
            )
            expected_binding = expected.bindings.get(thread_id)
            if expected_binding is not None and str(expected_binding["state"]) != str(
                item["state"]
            ):
                raise contract.WorkflowError(
                    f"context package thread {thread_id} state must match the collected "
                    "discussion state"
                )
        missing = sorted(expected_ids - seen)
        if missing:
            raise contract.WorkflowError(
                "context package thread registry is missing collected threads: "
                + ", ".join(missing)
            )
    else:
        if binding.get("ref") != expected.ref:
            raise contract.WorkflowError(
                "context package comparison ref must equal the retained prepare-local boundary"
            )
        if binding["head_sha"] != expected.head_sha:
            raise contract.WorkflowError(
                "context package head_sha must match the prepared snapshot"
            )
        sections = binding.get("sections")
        if sections is None or expected.sections is None:
            raise contract.WorkflowError(
                "local context package must bind the committed/staged/unstaged/untracked sections"
            )
        for key in ("committed", "staged", "unstaged", "untracked"):
            if str(sections[key]) != str(expected.sections[key]):
                raise contract.WorkflowError(
                    f"context package section {key} does not match the prepared snapshot"
                )
    if payload["goal"]["status"] == "known" and not _require_goal_text(payload["goal"]):
        raise contract.WorkflowError(
            "context package goal status known requires non-empty goal.text; keep status "
            "unknown when the task is unknown"
        )
    acceptance = payload["acceptance_criteria"]
    if acceptance["status"] == "known" and (
        not isinstance(acceptance.get("items"), list) or len(acceptance["items"]) == 0
    ):
        raise contract.WorkflowError(
            "context package acceptance status known requires at least one criterion"
        )
    claims = payload["claims"]
    claim_ids = {str(item["id"]) for item in claims}
    if len(claim_ids) != len(claims):
        raise contract.WorkflowError("context package claim IDs must be unique")
    for claim in claims:
        for disputed in claim.get("disputed_by") or []:
            if disputed not in claim_ids:
                raise contract.WorkflowError(
                    f"context package claim {claim['id']} disputes unknown claim {disputed}"
                )
    questions = payload["questions"]
    question_ids = {str(item["id"]) for item in questions}
    if len(question_ids) != len(questions):
        raise contract.WorkflowError("context package question IDs must be unique")
    _verify_question_contexts(payload)


def write_context_package(root: str | Path, payload: dict[str, Any]) -> tuple[Path, str]:
    path, digest_value = contract.write_artifact(Path(root), "context_package", payload)
    contract.write_json(
        package_pointer_path(root),
        {
            "package_path": str(path),
            "package_digest": digest_value,
            "evidence_digest": str(payload["binding"]["evidence_digest"]),
            "canonical_digest": canonical_package_digest(payload),
            "background_digest": narrative_package_digest(payload),
        },
    )
    return path, digest_value


def supersedes_digest(root: str | Path, supersedes: object) -> None:
    if supersedes is None:
        return
    pointer = read_package_pointer(root)
    previous_digest = None if pointer is None else str(pointer.get("package_digest") or "")
    if previous_digest != supersedes:
        raise contract.WorkflowError(
            "context package supersedes must name the currently recorded package digest"
        )
