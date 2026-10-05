"""Local WIP review: snapshots, incremental follow-up, and the panel flow."""

from __future__ import annotations

import copy
import difflib
import re
from pathlib import Path
from typing import Any, cast

from reviewmatic import context
from reviewmatic import draft as draft_module
from reviewmatic.context_package import (
    ExpectedPackage,
    bind_question_contexts,
    canonical_package_digest,
    collect_answers,
    extract_superseded_results,
    is_current_result,
    local_section_digests,
    narrative_package_digest,
    package_template_for_local,
    question_context_version_list,
    question_context_versions,
    question_report,
    read_package_pointer,
    recorded_package,
    supersedes_digest,
    validate_answers,
    validate_package_payload,
    validate_verifications,
    write_context_package,
)
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.portable.state_artifacts import content_digest
from reviewmatic.schema_issues import schema_issues

LOCAL_PANEL_DIR = "local-panel"


def _is_object(value: object) -> bool:
    return isinstance(value, dict)


def _truthy(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return len(value) > 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return True


def _python_get(target: dict[str, Any], key: str) -> object:
    return target.get(key)


def _compare_code_points(left: str, right: str) -> int:
    first = list(left)
    second = list(right)
    for a, b in zip(first, second, strict=False):
        if ord(a) != ord(b):
            return ord(a) - ord(b)
    return len(first) - len(second)


def _addressed_payload(root: str, kind: str, digest_value: str) -> dict[str, Any]:
    if not contract.is_digest(digest_value):
        raise contract.WorkflowError("local review artifact digest is invalid")
    envelope, payload = contract.artifact_payload(
        Path(root) / "artifacts" / kind / f"{digest_value}.json", kind
    )
    if contract.digest(envelope) != digest_value:
        raise contract.WorkflowError("local review artifact digest does not match its content")
    return payload


def baseline(root: str) -> tuple[str | None, dict[str, Any] | None, str]:
    pointer = Path(root) / "local-review.json"
    present = pointer.exists() or pointer.is_symlink()
    if not present:
        return None, None, "no_previous_review"
    try:
        value = contract.read_json(pointer, "local review pointer")
        review_digest = _python_get(value, "review_digest")
        if not isinstance(review_digest, str) or not contract.is_digest(review_digest):
            raise contract.WorkflowError("local review pointer has no valid digest")
        report = _addressed_payload(root, "local_review_report", review_digest)
        validate_report(report)
    except contract.WorkflowError:
        return None, None, "previous_review_unavailable"
    return review_digest, report, "previous_review_available"


def _compatible(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return (
        previous.get("retrieval_complete") is True
        and current.get("retrieval_complete") is True
        and all(
            _python_get(previous, key) == _python_get(current, key)
            for key in ("repo_root", "profile", "base_sha", "head_sha", "ref", "artifact_root")
        )
    )


def _split_keep_ends(value: str) -> list[str]:
    # Preserve line terminators so generated snapshots remain byte-accurate.
    return value.splitlines(keepends=True)


def _format_range_unified(start: int, stop: int) -> str:
    # difflib's own range formatting, inlined for a typed public equivalent.
    beginning = start + 1
    length = stop - start
    if length == 1:
        return f"{beginning}"
    if length == 0:
        return f"{beginning - 1},0"
    return f"{beginning},{length}"


def _unified_diff(before: str, after: str, from_file: str, to_file: str) -> str:
    # Keep the context width and autojunk behavior explicit for stable output.
    before_lines = _split_keep_ends(before)
    after_lines = _split_keep_ends(after)
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    lines: list[str] = []
    for group in matcher.get_grouped_opcodes(3):
        if not lines:
            lines.extend([f"--- {from_file}\n", f"+++ {to_file}\n"])
        first, last = group[0], group[-1]
        lines.append(
            f"@@ -{_format_range_unified(first[1], last[2])} "
            f"+{_format_range_unified(first[3], last[4])} @@\n"
        )
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                lines.extend(f" {line}" for line in before_lines[i1:i2])
                continue
            lines.extend(f"-{line}" for line in before_lines[i1:i2])
            lines.extend(f"+{line}" for line in after_lines[j1:j2])
    return "".join(lines)


def _section_delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    previous_sections = cast("dict[str, dict[str, Any]]", previous["sections"])
    current_sections = cast("dict[str, dict[str, Any]]", current["sections"])
    for name in ("committed", "staged", "unstaged"):
        before = previous_sections[name]
        after = current_sections[name]
        if contract.digest(before) != contract.digest(after):
            delta[name] = _unified_diff(
                str(before["diff"]), str(after["diff"]), f"previous/{name}", f"current/{name}"
            )
    previous_items = {
        str(item["path"]): item
        for item in cast("list[dict[str, Any]]", previous_sections["untracked"]["items"])
    }
    after_items = {
        str(item["path"]): item
        for item in cast("list[dict[str, Any]]", current_sections["untracked"]["items"])
    }
    paths = sorted(set(previous_items) | set(after_items), key=lambda p: tuple(map(ord, p)))
    changed = [
        {
            "path": path,
            "before": previous_items.get(path),
            "after": after_items.get(path),
        }
        for path in paths
        if contract.digest(previous_items.get(path)) != contract.digest(after_items.get(path))
    ]
    if changed:
        delta["untracked"] = changed
    return delta


# Pure computation behind prepareFollowup: baseline selection, reuse mode,
# section delta, and the report/package templates. No file is written, so
# read-only consumers (scope-review) can reconstruct the exact prepared view
# without mutating preparation state.
def local_followup_plan(
    root: str, bundle: dict[str, Any], digest_value: str, incremental: str
) -> dict[str, Any]:
    previous_digest, report, initial_reason = baseline(root)
    reason = initial_reason
    prior: dict[str, Any] | None = None
    if report is not None:
        try:
            prior = _addressed_payload(root, "local_wip_snapshot", str(report["evidence_digest"]))
        except contract.WorkflowError:
            reason = "previous_evidence_unavailable"
    reusable = prior is not None and _compatible(prior, bundle)
    delta: dict[str, Any] = {}
    if reusable and prior is not None:
        delta = _section_delta(prior, bundle)
    mode = "full"
    if reusable and incremental == "auto":
        mode = "incremental" if delta else "unchanged"
        reason = "changed_local_evidence" if delta else "unchanged_local_evidence"
    elif incremental == "off":
        reason = "explicit_full_review"
    elif prior is not None and not reusable:
        reason = "incompatible_boundary_or_incomplete_evidence"
    retained: dict[str, Any] | None = report if reusable else None
    package_template = package_template_for_local(bundle, digest_value, retained)
    template = {
        "evidence_digest": digest_value,
        "previous_review_digest": previous_digest,
        "mode": mode,
        "context_package": None,
        "question_answers": [],
        "question_verifications": [],
        "task": copy.deepcopy(cast("dict[str, Any]", retained["task"]))
        if retained is not None
        else {
            "goal": "",
            "acceptance_criteria": [],
            "constraints": [],
            "accepted_risks": [],
            "deferred": [],
            "decision_evidence": "",
        },
        "task_change_reason": None,
        "findings": copy.deepcopy(cast("list[dict[str, Any]]", retained["findings"]))
        if retained is not None
        else [],
        "checks": [],
        "assessment": "",
        "verdict": "blocked",
        "external_mutations": False,
    }
    recorded = recorded_package(root)
    package_current = (
        recorded is not None
        and recorded["payload"]["mode"] == "local"
        and str(cast("dict[str, Any]", recorded["payload"]["binding"])["evidence_digest"])
        == digest_value
    )
    snapshot_path = f"{root}/artifacts/local_wip_snapshot/{digest_value}.json"
    return {
        "mode": mode,
        "reason": reason,
        "baseline_compatible": reusable,
        "previous_review_digest": previous_digest,
        "previous_report": report,
        "previous_evidence_digest": report["evidence_digest"] if report else None,
        "previous_ref": _python_get(prior, "ref") if prior is not None else None,
        "delta": delta,
        "report_template": template,
        "draft_path": f"{root}/local-review-draft.json",
        "context_package": {
            "template_path": f"{root}/local-context-package-input.json",
            "package_path": None if recorded is None else recorded["path"],
            "package_digest": None if recorded is None else recorded["digest"],
            "status": "recorded" if package_current else "pending",
            "question_context_versions": (
                question_context_version_list(recorded["payload"])
                if package_current and recorded is not None
                else None
            ),
            "record_command": context.runner_action(
                "record-package",
                "--bundle",
                snapshot_path,
                "--input",
                f"{root}/local-context-package-input.json",
            )["command"],
        },
        "package_template_payload": package_template,
    }


def prepare_followup(
    root: str, bundle: dict[str, Any], digest_value: str, incremental: str
) -> dict[str, Any]:
    plan = local_followup_plan(root, bundle, digest_value, incremental)
    contract.write_json(
        Path(root) / "local-context-package-input.json",
        cast("dict[str, Any]", plan["package_template_payload"]),
    )
    return {key: value for key, value in plan.items() if key != "package_template_payload"}


# Selects the local review draft for the current snapshot: an existing draft
# bound to this exact evidence is reused verbatim (unfinished work survives),
# while a missing or stale draft is re-materialized from the pure follow-up
# plan, so runtime-owned fields always follow the current snapshot and
# baseline instead of a previous cycle's mechanical bindings.
def select_local_draft(
    root: str,
    bundle: dict[str, Any],
    digest_value: str,
    incremental: str = "auto",
) -> dict[str, Any]:
    plan = local_followup_plan(root, bundle, digest_value, incremental)
    draft_path = Path(root) / "local-review-draft.json"
    if draft_path.exists():
        found = contract.read_json(draft_path, "local review draft")
        if _python_get(found, "evidence_digest") == digest_value:
            return {"draft": found, "materialized": False, "plan": {}}
        # A fresh preparation of identical evidence content (the envelope digest
        # changes through its creation stamp alone) adopts the unfinished draft:
        # runtime-owned fields follow the new snapshot while every agent section
        # survives, and the recorded package's authored content is carried into
        # the new template so re-recording stays mechanical.
        current_digest = _python_get(found, "evidence_digest")
        if isinstance(current_digest, str) and contract.is_digest(current_digest):
            try:
                prior = _addressed_payload(root, "local_wip_snapshot", current_digest)
                same_boundary = (
                    _python_get(prior, "repo_root") == _python_get(bundle, "repo_root")
                    and _python_get(prior, "base_sha") == _python_get(bundle, "base_sha")
                    and _python_get(prior, "head_sha") == _python_get(bundle, "head_sha")
                    and _python_get(prior, "ref") == _python_get(bundle, "ref")
                )
                if same_boundary and not _section_delta(prior, bundle):
                    adopted = copy.deepcopy(found)
                    adopted["evidence_digest"] = digest_value
                    adopted["previous_review_digest"] = plan["previous_review_digest"]
                    adopted["mode"] = plan["mode"]
                    adopted["context_package"] = None
                    recorded = recorded_package(root)
                    if (
                        recorded is not None
                        and str(
                            cast("dict[str, Any]", recorded["payload"]["binding"])[
                                "evidence_digest"
                            ]
                        )
                        == current_digest
                    ):
                        fresh = copy.deepcopy(
                            cast("dict[str, Any]", plan["package_template_payload"])
                        )
                        for key in (
                            "goal",
                            "acceptance_criteria",
                            "background",
                            "claims",
                            "constraints",
                            "prior_decisions",
                            "questions",
                            "supersedes",
                        ):
                            fresh[key] = copy.deepcopy(recorded["payload"].get(key, fresh.get(key)))
                        plan["package_template_payload"] = fresh
                        contract.write_json(Path(root) / "local-context-package-input.json", fresh)
                    return {"draft": adopted, "materialized": True, "plan": plan}
            except contract.WorkflowError:
                # A prior snapshot that cannot be read falls back to re-materializing.
                pass
    draft = copy.deepcopy(cast("dict[str, Any]", plan["report_template"]))
    context_package = cast("dict[str, Any]", plan["context_package"])
    if context_package["status"] == "recorded":
        draft["context_package"] = {
            "path": context_package["package_path"],
            "digest": context_package["package_digest"],
        }
    # Historical superseded results are evidence, never mechanical bindings:
    # a stale draft's history survives the snapshot change.
    if draft_path.exists():
        try:
            stale = contract.read_json(draft_path, "local review draft")
            history = stale.get("superseded_question_results")
            if isinstance(history, list) and len(history) > 0:
                draft["superseded_question_results"] = history
        except contract.WorkflowError:
            # A unreadable stale draft is replaced, not trusted.
            pass
    return {"draft": draft, "materialized": True, "plan": plan}


# Persists a selected draft. A re-materialized draft also refreshes the
# package template unless the on-disk template already binds this snapshot,
# in which case agent edits to it are preserved.
def persist_local_draft(
    root: str,
    digest_value: str,
    selection: dict[str, Any],
    local_draft: dict[str, Any],
) -> None:
    contract.write_json(Path(root) / "local-review-draft.json", local_draft)
    if not selection["materialized"]:
        return
    template_path = Path(root) / "local-context-package-input.json"
    keep = False
    if template_path.exists():
        try:
            template = contract.read_json(template_path, "local context package template")
            binding = _python_get(template, "binding")
            keep = (
                isinstance(binding, dict)
                and _python_get(binding, "evidence_digest") == digest_value
            )
        except contract.WorkflowError:
            keep = False
    if not keep:
        contract.write_json(
            template_path, cast("dict[str, Any]", selection["plan"]["package_template_payload"])
        )


def _validate_finding(finding: dict[str, Any]) -> None:
    if _truthy(finding.get("blocking")) and finding.get("status") != "open":
        raise contract.WorkflowError("only open findings can block local acceptance")
    if finding.get("status") == "accepted_risk" and not _truthy(finding.get("decision_evidence")):
        raise contract.WorkflowError("accepted risk requires the user's decision evidence")
    if (
        _truthy(finding.get("blocking"))
        and (finding.get("origin") == "new_requirement" or finding.get("origin") == "pre_existing")
        and not _truthy(finding.get("decision_evidence"))
    ):
        raise contract.WorkflowError("scope expansion requires explicit decision evidence")


# The derived local verdict for a set of findings and checks; shared by the
# report validator and the arbitration import so the arbitrator's verdict can
# never disagree with the recorded evidence.
def _expected_local_verdict(findings: list[dict[str, Any]], checks: list[dict[str, Any]]) -> str:
    required = [check for check in checks if _truthy(check.get("required"))]
    if not required:
        return "blocked"
    if any(check.get("status") == "not_run" for check in required):
        return "blocked"
    if any(check.get("status") == "failed" for check in required) or any(
        _truthy(finding.get("blocking")) for finding in findings
    ):
        return "not_ready"
    return "ready"


def validate_report(report: dict[str, Any]) -> None:
    schema = contract.artifact_schema()
    defs = cast("dict[str, Any]", schema["$defs"])
    issues = schema_issues(
        cast("dict[str, Any]", defs["local_review_payload"]), report, "$", schema
    )
    if issues:
        raise contract.WorkflowError(
            "local review report is invalid:\n"
            + "\n".join(f" - {issue['path']}: {issue['message']}" for issue in issues)
        )
    findings = cast("list[dict[str, Any]]", report["findings"])
    ids = [str(finding["id"]) for finding in findings]
    if len(ids) != len(set(ids)):
        raise contract.WorkflowError("local review finding IDs must be unique")
    for finding in findings:
        _validate_finding(finding)
    checks = cast("list[dict[str, Any]]", report["checks"])
    if not any(_truthy(check.get("required")) for check in checks):
        raise contract.WorkflowError("local review must include required acceptance checks")
    expected = _expected_local_verdict(findings, checks)
    if report["verdict"] != expected:
        raise contract.WorkflowError(
            f"local review verdict must be {expected} for the recorded evidence"
        )


def _validate_continuity(report: dict[str, Any], previous: dict[str, Any]) -> None:
    if contract.digest(report["task"]) != contract.digest(previous["task"]) and not _truthy(
        report.get("task_change_reason")
    ):
        raise contract.WorkflowError(
            "changed task boundary requires decision evidence in task_change_reason"
        )
    findings = {
        str(finding["id"]): finding for finding in cast("list[dict[str, Any]]", report["findings"])
    }
    for old in cast("list[dict[str, Any]]", previous["findings"]):
        updated = findings.get(str(old["id"]))
        if updated is None:
            raise contract.WorkflowError(
                "previous findings must retain their stable IDs and dispositions"
            )
        reopened = updated.get("status") == "open" and (
            old.get("status") != "open"
            or (_truthy(updated.get("blocking")) and not _truthy(old.get("blocking")))
        )
        if reopened:
            changed_basis = any(
                updated.get(key) != old.get(key) for key in ("requirement", "scenario", "evidence")
            ) or (
                contract.digest(report["task"]) != contract.digest(previous["task"])
                and _truthy(report.get("task_change_reason"))
            )
            changed_decision = _truthy(updated.get("decision_evidence")) and updated.get(
                "decision_evidence"
            ) != old.get("decision_evidence")
            if not _truthy(updated.get("reopen_reason")) or not (changed_basis or changed_decision):
                raise contract.WorkflowError(
                    "reopening a finding requires changed facts or a user decision"
                )


def _local_section(root: str, name: str, arguments: list[str]) -> dict[str, Any]:
    value = str(contract.git_read(Path(root), *arguments))
    return {
        "name": name,
        "diff": value,
        "sha256": content_digest(value.encode()),
        "complete": True,
        "errors": [],
    }


def _local_untracked(root: str) -> dict[str, Any]:
    raw = contract.git_read(
        Path(root), "ls-files", "--others", "--exclude-standard", "-z", text=False
    )
    encoded_paths = raw.split(b"\x00") if isinstance(raw, bytes) else []
    items: list[dict[str, Any]] = []
    errors: list[str] = []

    def record_incomplete(relative: str, reason: str, size: int | None = None) -> None:
        item: dict[str, Any] = {"path": relative, "complete": False, "reason": reason}
        if size is not None:
            item["size"] = size
        items.append(item)
        errors.append(relative)

    for encoded in encoded_paths:
        if len(encoded) == 0:
            continue
        relative = encoded.decode("utf-8", errors="surrogateescape")
        candidate = Path(root) / relative
        try:
            meta = candidate.lstat()
        except OSError:
            record_incomplete(relative, "unreadable")
            continue
        if candidate.is_symlink():
            record_incomplete(relative, "symlink")
            continue
        if not candidate.is_file():
            record_incomplete(relative, "non_regular")
            continue
        if meta.st_size > contract.MAX_BYTES:
            record_incomplete(relative, "oversized", meta.st_size)
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            record_incomplete(relative, "unreadable")
            continue
        if b"\x00" in data:
            record_incomplete(relative, "binary", len(data))
            continue
        items.append(
            {
                "path": relative,
                "size": len(data),
                "sha256": content_digest(data),
                "complete": True,
            }
        )
    return {"items": items, "complete": not errors, "errors": errors}


def empty_scope_reason(bundle: dict[str, Any]) -> str | None:
    if bundle.get("retrieval_complete") is not True:
        return None
    sections = cast("dict[str, dict[str, Any]]", bundle["sections"])
    untracked = sections["untracked"]
    uncommitted_work_empty = (
        len(str(sections["staged"]["diff"])) == 0
        and len(str(sections["unstaged"]["diff"])) == 0
        and len(cast("list[dict[str, Any]]", untracked["items"])) == 0
    )
    if not uncommitted_work_empty:
        return None
    if bundle.get("ref") is None:
        return "no_uncommitted_changes"
    return "no_changes_relative_to_ref" if len(str(sections["committed"]["diff"])) == 0 else None


def _short_ref_candidates(root: str, ref: str) -> list[str]:
    names = {
        f"refs/{ref}",
        f"refs/heads/{ref}",
        f"refs/tags/{ref}",
        f"refs/remotes/{ref}",
    }
    return [
        name.strip()
        for name in str(contract.git_read(Path(root), "for-each-ref", "--format=%(refname)")).split(
            "\n"
        )
        if name.strip() in names
    ]


# Revision expressions such as `dup~0` resolve through the ambiguous short
# name without warning, so ambiguity is decided for the expression's base
# name, not only for a literal refname.
def _comparison_base_name(ref: str) -> str:
    return re.split(r"[~^:@]", ref, maxsplit=1)[0]


def _comparison_base(root: str, ref: str) -> str:
    if not ref.startswith("refs/"):
        base = _comparison_base_name(ref)
        candidates = [] if base in ("", "HEAD") else _short_ref_candidates(root, base)
        if len(candidates) > 1:
            raise contract.WorkflowError(
                f"comparison ref '{ref}' is ambiguous in the local checkout "
                f"({', '.join(candidates)}); ask which revision to use or pass one full "
                "refname; the runner does not fetch or choose for you"
            )
    try:
        contract.git_read(Path(root), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except contract.WorkflowError:
        raise contract.WorkflowError(
            f"comparison ref '{ref}' was not found or is not a commit in the local checkout; "
            "pass an existing local revision; the runner does not fetch or substitute one"
        ) from None
    try:
        return str(contract.git_read(Path(root), "merge-base", ref, "HEAD")).strip()
    except contract.WorkflowError:
        raise contract.WorkflowError(
            f"no common merge base between '{ref}' and HEAD in the local checkout; ask how to "
            "proceed instead of falling back; the runner does not fetch"
        ) from None


def local_bundle(repo_root: str, profile: str, ref: str | None) -> dict[str, Any]:
    raw_path = Path(repo_root)
    if raw_path.is_symlink():
        raise contract.WorkflowError("repo root must not be a symbolic link")
    root = str(raw_path.resolve())
    if not (Path(root) / ".git").exists():
        raise contract.WorkflowError("repo root must be a real Git checkout")
    try:
        head = str(contract.git_read(Path(root), "rev-parse", "HEAD")).strip()
    except contract.WorkflowError:
        raise contract.WorkflowError(
            "the checkout has no readable HEAD; the repository needs at least one commit"
        ) from None
    base = _comparison_base(root, ref) if ref else head
    staged = _local_section(
        root, "staged", ["diff", "--cached", "--binary", "--find-renames", "--"]
    )
    unstaged = _local_section(root, "unstaged", ["diff", "--binary", "--find-renames", "--"])
    untracked = _local_untracked(root)
    committed = _local_section(
        root,
        "committed",
        ["diff", "--binary", "--find-renames", base, head, "--"]
        if ref
        else ["diff", "--binary", "--find-renames", "HEAD", "HEAD", "--"],
    )
    identity = {"hostname": "local", "project_path": root, "kind": "local", "iid": 1}
    artifact = contract.state_directory(profile, identity)
    sections: dict[str, dict[str, Any]] = {
        "committed": committed,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }
    return {
        "schema_version": contract.ARTIFACT_VERSION,
        "profile": profile,
        "external_mutations": False,
        "repo_root": root,
        "base_sha": base,
        "head_sha": head,
        "ref": ref,
        "sections": sections,
        "artifact_root": str(artifact),
        "retrieval_complete": all(
            _truthy(section.get("complete")) for section in sections.values()
        ),
    }


def finalize_local(bundle_file: str) -> dict[str, Any]:
    _, baseline_payload = contract.artifact_payload(Path(bundle_file), "local_wip_snapshot")
    root = baseline_payload.get("repo_root")
    if not isinstance(root, str):
        raise contract.WorkflowError("local evidence identity is incomplete")
    ref = _python_get(baseline_payload, "ref")
    if ref is not None and not isinstance(ref, str):
        raise contract.WorkflowError("local evidence ref is invalid")
    profile = baseline_payload.get("profile", "code-review")
    current = local_bundle(root, str(profile), ref)
    changed = [
        key
        for key in ("base_sha", "head_sha", "ref", "sections", "retrieval_complete")
        if contract.digest(_python_get(baseline_payload, key)) != contract.digest(current.get(key))
    ]
    return {
        "status": "ok" if not changed and _truthy(current.get("retrieval_complete")) else "stale",
        "changed": changed,
        "head_sha": current["head_sha"],
        "complete": current["retrieval_complete"],
    }


_LOCAL_SECTIONS = (
    "task",
    "task_change_reason",
    "findings",
    "checks",
    "assessment",
    "verdict",
    "question_answers",
    "question_verifications",
)

_LOCAL_DEFS = cast("dict[str, Any]", contract.artifact_schema()["$defs"])
_LOCAL_PROPERTIES = cast(
    "dict[str, Any]", cast("dict[str, Any]", _LOCAL_DEFS["local_review_payload"])["properties"]
)
_LOCAL_FINDING_ITEMS = cast("dict[str, Any]", _LOCAL_PROPERTIES["findings"])["items"]
_LOCAL_CHECK_ITEMS = cast("dict[str, Any]", _LOCAL_PROPERTIES["checks"])["items"]

_LOCAL_CRITIC_RECEIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema",
        "evidence_digest",
        "run_id",
        "session_id",
        "findings",
        "external_mutations",
    ],
    "additionalProperties": False,
    "properties": {
        "schema": {"const": "code-review/local-critic-receipt/v1"},
        "evidence_digest": {"$ref": "#/$defs/digest"},
        "run_id": {"type": "string", "minLength": 1},
        "session_id": {"type": "string", "minLength": 1},
        "findings": {"type": "array", "items": _LOCAL_FINDING_ITEMS},
        "question_answers": {"type": "array", "items": {"$ref": "#/$defs/context_answer_ref"}},
        "external_mutations": {"const": False},
    },
}

_LOCAL_ARBITRATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema",
        "evidence_digest",
        "run_id",
        "session_id",
        "external_mutations",
        "findings",
        "dispositions",
        "checks",
        "assessment",
        "verdict",
    ],
    "additionalProperties": False,
    "properties": {
        "schema": {"const": "code-review/local-arbitration/v1"},
        "evidence_digest": {"$ref": "#/$defs/digest"},
        "run_id": {"type": "string", "minLength": 1},
        "session_id": {"type": "string", "minLength": 1},
        "arbitrator": {"type": "object"},
        "external_mutations": {"const": False},
        "findings": {"type": "array", "items": _LOCAL_FINDING_ITEMS},
        "dispositions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "decision", "reason"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "decision": {"enum": ["accept", "reject"]},
                    "reason": {"type": "string", "minLength": 1},
                    "duplicate_of": {"type": "string", "minLength": 1},
                },
            },
        },
        "question_verifications": {
            "type": "array",
            "items": {"$ref": "#/$defs/context_verification"},
        },
        "checks": {"type": "array", "items": _LOCAL_CHECK_ITEMS},
        "assessment": {"type": "string", "minLength": 1},
        "verdict": {"enum": ["ready", "not_ready", "blocked"]},
    },
}


# Mechanical assembly for the local review draft. Works on the prepared local
# report template exactly like record-input works on the MR draft: semantic
# sections only, machine bindings preserved, no verdict invented.
def _local_gaps(report: dict[str, Any]) -> dict[str, Any]:
    checks = cast("list[dict[str, Any]]", report.get("checks") or [])
    required = [check for check in checks if check.get("required") is True]
    binding = cast("dict[str, Any] | None", report.get("context_package"))
    return {
        "checks_required_total": len(required),
        "checks_not_run": sum(1 for check in required if check.get("status") == "not_run"),
        "checks_failed": sum(1 for check in required if check.get("status") == "failed"),
        "assessment_empty": (
            ["$.assessment"]
            if not isinstance(report.get("assessment"), str) or report["assessment"] == ""
            else []
        ),
        "context_package": (
            []
            if binding is not None
            else ["not recorded; run record-package --bundle before finalize-local"]
        ),
        "question_answers": len(cast("list[dict[str, Any]]", report.get("question_answers") or [])),
        "question_verifications": len(
            cast("list[dict[str, Any]]", report.get("question_verifications") or [])
        ),
    }


# Stable canonical form for comparing stored and resent results: object key
# order must never decide whether a repeated result is a duplicate.
def _stable_value(value: object) -> object:
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _stable_value(value[key])
            for key in sorted(value, key=lambda item: tuple(map(ord, item)))
        }
    return value


# Full identity of one collected result: the question, the meaningful-context
# version it was produced against, and the authoring run/session. Critic
# answers additionally keep the critic's own identity, while a primary
# verification is identified by the preserved original answer it verifies.
def _result_identity(section: str, item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    origin = item if section == "question_answers" else item.get("original")
    if not isinstance(origin, dict):
        return None
    parts = (
        item.get("question_id"),
        item.get("context_digest"),
        origin.get("run_id"),
        origin.get("session_id"),
    )
    if any(not isinstance(part, str) or part == "" for part in parts):
        return None
    return "\x00".join(cast("list[str]", parts))


# Merges sequentially imported critic answers (and the primary's
# verifications) into the stored list instead of replacing it: a repeated
# identical result is not duplicated, a different result with the same critic
# identity and context version is rejected while the original is preserved,
# and the primary may revise its own verification in place. Every other entry
# survives regardless of order or disagreement.
def _merge_result_entries(
    current: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    section: str,
    issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    result = copy.deepcopy(current)
    positions: dict[str, int] = {}
    for index, item in enumerate(result):
        identity = _result_identity(section, item)
        if identity is not None and identity not in positions:
            positions[identity] = index
    for index, item in enumerate(incoming):
        identity = _result_identity(section, item)
        if identity is None:
            continue  # the schema issues already name the entry
        stored = result[positions[identity]] if identity in positions else None
        if stored is None:
            positions[identity] = len(result)
            result.append(item)
            continue
        if contract.digest(_stable_value(stored)) == contract.digest(_stable_value(item)):
            continue
        if section == "question_verifications":
            result[positions[identity]] = item
            continue
        question = str(item["question_id"])
        issues.append(
            {
                "path": f"$.question_answers[{index}]",
                "message": (
                    f"An answer for question {question} with this critic run/session identity and "
                    "context version is already recorded with a different result; the original is "
                    "preserved. Import the other critic's result under its own identity, or record "
                    "the primary resolution in question_verifications preserving the original answer"
                ),
            }
        )
    return result


def _canonical_snapshot_check(bundle_path: str, root: str, digest_value: str, label: str) -> None:
    if str(Path(bundle_path).resolve()) != (
        f"{root}/artifacts/local_wip_snapshot/{digest_value}.json"
    ):
        raise contract.WorkflowError(f"{label} the canonical immutable local snapshot")


def _snapshot_envelope(bundle_path: str) -> tuple[dict[str, Any], str]:
    _, bundle = contract.artifact_payload(Path(bundle_path), "local_wip_snapshot")
    envelope = contract.read_json(Path(bundle_path), "local evidence")
    return bundle, contract.digest(envelope)


def _panel_complete(local_draft: dict[str, Any]) -> bool:
    if not isinstance(local_draft.get("participants"), dict):
        return False
    critics = cast("dict[str, Any]", local_draft["participants"]).get("critics")
    if not isinstance(critics, list):
        return False
    receipts = cast("list[dict[str, Any]]", local_draft.get("critics") or [])
    return len(receipts) == len(critics) and all(
        isinstance(item.get("receipt"), dict) for item in critics
    )


def _panel_critic_tasks(local_draft: dict[str, Any], bundle_path: str) -> list[dict[str, Any]]:
    critics = cast(
        "list[dict[str, Any]]",
        cast("dict[str, Any]", local_draft["participants"]).get("critics") or [],
    )
    return [
        {
            "participant": str(critic["name"]),
            "profile": critic.get("profile"),
            "provider": critic.get("provider"),
            "model": critic.get("model"),
            "receipt_schema": "code-review/local-critic-receipt/v1",
            "template": {
                "schema": "code-review/local-critic-receipt/v1",
                "evidence_digest": local_draft["evidence_digest"],
                "run_id": "",
                "session_id": "",
                "findings": [],
                "question_answers": [],
                "external_mutations": False,
            },
            "import_command": context.runner_action(
                "record-critic",
                "--bundle",
                bundle_path,
                "--input",
                "<local-critic-response.json>",
                "--participant",
                str(critic["name"]),
            ),
            "rules": (
                "One receipt per selected critic: a complete independent local review with "
                "findings in the local report shape and one question_answers entry per "
                "critic-assigned question, every answer copying that question's context_digest. "
                "Critics run in parallel, never see each other's output, and read the working "
                "tree exactly as committed, staged, and untracked in the recorded snapshot "
                "without recollecting anything."
            ),
        }
        for critic in critics
    ]


# Materializes the local arbitrator's input and returns its launch task once
# every selected critic receipt is imported and bound.
def _sync_local_arbitration_input(
    local_draft: dict[str, Any], root: str, bundle_path: str
) -> dict[str, Any] | None:
    if not _panel_complete(local_draft):
        return None
    binding = cast("dict[str, Any] | None", local_draft.get("context_package"))
    if not isinstance(binding, dict):
        return None
    _, package_payload = contract.artifact_payload(Path(str(binding["path"])), "context_package")
    questions = cast("list[dict[str, Any]]", package_payload.get("questions") or [])
    answers, contradictions = collect_answers(
        cast("list[dict[str, Any]]", local_draft.get("critics") or [])
    )
    verifications = cast("list[dict[str, Any]]", local_draft.get("question_verifications") or [])
    input_path = Path(root) / "local-arbitration-input.json"
    contract.write_json(
        input_path,
        {
            "schema": "code-review/local-arbitration-input/v1",
            "evidence_digest": local_draft["evidence_digest"],
            "context_package": {
                "path": binding["path"],
                "digest": binding["digest"],
                "question_context_versions": question_context_version_list(package_payload),
            },
            "inputs": {"bundle_path": bundle_path, "repo_root": local_draft.get("repo_root")},
            "participants": copy.deepcopy(local_draft["participants"]),
            "previous_findings": copy.deepcopy(
                cast("list[dict[str, Any]]", local_draft.get("findings") or [])
            ),
            "task": copy.deepcopy(local_draft.get("task")),
            "critic_receipts": copy.deepcopy(
                cast("list[dict[str, Any]]", local_draft.get("critics") or [])
            ),
            "question_report": question_report(questions, answers, verifications),
            "contradictions": contradictions,
            "response_contract": {
                "receipt_schema": "code-review/local-arbitration/v1",
                "import_command": context.runner_action(
                    "record-arbitration",
                    "--bundle",
                    bundle_path,
                    "--input",
                    "<local-arbitration-receipt.json>",
                ),
                "rules": (
                    "One receipt with a verdict for every critic finding and every merged "
                    "finding, targeted evidence checks for contradictions, merged findings that "
                    "retain prior stable IDs, and the consolidated checks, assessment, and verdict."
                ),
            },
        },
    )
    return {
        "launch": "now_after_every_critic_receipt",
        "input_path": str(input_path),
        "instructions": (
            "Launch the selected local arbitrator subagent now. It receives the arbitration "
            "input, the recorded package, and the snapshot's working-tree state. It confirms or "
            "refutes every critic finding with a concrete reason, resolves contradictions with "
            "targeted checks, merges duplicates without losing authors, keeps prior finding IDs "
            "stable, and records the consolidated checks, assessment, and verdict. It never "
            "starts a new defect search from scratch and never modifies the working tree."
        ),
    }


# Records the agent-authored context package for a prepared local snapshot.
# Purely mechanical validation and binding; no network, fetch, or worktree.
def record_local_package(bundle_path: str, input_path: str) -> dict[str, Any]:
    bundle, digest_value = _snapshot_envelope(bundle_path)
    root = str(bundle["artifact_root"])
    _canonical_snapshot_check(bundle_path, root, digest_value, "context package requires")
    user_input = contract.read_json(
        contract.regular_file(Path(input_path), "context package input"), "context package input"
    )
    validate_package_payload(
        user_input,
        ExpectedPackage(
            mode="local",
            evidence_digest=digest_value,
            artifact_root=root,
            repo_root=str(bundle["repo_root"]),
            head_sha=str(bundle["head_sha"]),
            ref=cast("str | None", _python_get(bundle, "ref")),
            sections=local_section_digests(bundle),
        ),
    )
    # Stamp the meaningful-context version onto every question before the
    # package becomes immutable; report answers carry the stamp they saw.
    bind_question_contexts(user_input)
    supersedes_digest(root, user_input.get("supersedes"))
    previous_pointer = read_package_pointer(root)
    package_path, package_digest = write_context_package(root, user_input)
    # Bind the recorded package into the draft selected for this snapshot,
    # materializing it when needed; the agent never copies package paths or
    # digests by hand, in either order of record-package and record-input.
    selection = select_local_draft(root, bundle, digest_value)
    selected_draft = cast("dict[str, Any]", selection["draft"])
    superseded = _retire_superseded_results(selected_draft, previous_pointer, user_input)
    selected_draft["context_package"] = {"path": str(package_path), "digest": package_digest}
    panel_tasks = (
        _panel_critic_tasks(selected_draft, bundle_path)
        if isinstance(selected_draft.get("participants"), dict)
        else None
    )
    persist_local_draft(root, digest_value, selection, selected_draft)
    return {
        "status": "ok",
        "artifact_path": str(package_path),
        "digest": package_digest,
        "canonical_digest": canonical_package_digest(user_input),
        "background_digest": narrative_package_digest(user_input),
        "question_context_versions": question_context_version_list(user_input),
        "question_summary": question_report(
            cast("list[dict[str, Any]]", user_input.get("questions") or []), [], []
        ),
        "superseded_questions": superseded,
        "critic_task": {
            "launch": "now",
            "mode": "local",
            "context_package": {
                "path": str(package_path),
                "digest": package_digest,
                "question_context_versions": question_context_version_list(user_input),
            },
            "inputs": {"repo_root": bundle["repo_root"], "bundle_path": bundle_path},
            "response_contract": {
                "answers_field": "$.question_answers",
                "import_command": context.runner_action(
                    "record-input",
                    "--bundle",
                    bundle_path,
                    "--input",
                    "<local-review-input.json>",
                ),
                "rules": (
                    "Every question_answer copies that question's context_digest listed above "
                    "and carries the critic's real run/session identity. The primary imports "
                    "answers (and any critic findings) with record-input without rewriting them."
                ),
            },
            "instructions": (
                "Launch the independent local critic now, alongside primary inspection, and "
                "join before finalize-local. The critic reads the recorded package as its "
                "primary task context and the working tree exactly as committed/staged/unstaged "
                "in the snapshot."
            ),
        },
        **(
            {
                "critic_tasks": panel_tasks,
                "arbitrator_task_hint": (
                    "After every selected critic receipt is imported, the record-critic response "
                    "returns the ready local arbitrator task; import its receipt with "
                    "record-arbitration"
                ),
            }
            if panel_tasks is not None
            else {}
        ),
        "external_mutations": False,
    }


def record_local_input(bundle_path: str, input_path: str) -> dict[str, Any]:
    bundle, digest_value = _snapshot_envelope(bundle_path)
    root = str(bundle["artifact_root"])
    _canonical_snapshot_check(bundle_path, root, digest_value, "record-input requires")
    draft_path = f"{root}/local-review-draft.json"
    user_input = contract.read_json(
        contract.regular_file(Path(input_path), "local draft input"), "local draft input"
    )
    contract.reject_envelope_wrapper(user_input, "local draft input")
    properties = cast("dict[str, dict[str, Any]]", _LOCAL_PROPERTIES)
    # Form is checked before any list is iterated or any field is read, so a
    # malformed section can only produce addressed diagnostics, never a crash.
    issues: list[dict[str, str]] = []
    valid_sections: list[tuple[str, object]] = []
    selection = select_local_draft(root, bundle, digest_value)
    selected_draft = cast("dict[str, Any]", selection["draft"])
    # In panel mode the orchestrating session owns no review semantics: the
    # arbitrator's receipt carries findings, checks, assessment, verdict, and
    # answer resolutions; record-input still carries the task boundary.
    if isinstance(selected_draft.get("participants"), dict):
        for key in user_input:
            if key not in {"task", "task_change_reason"}:
                issues.append(
                    {
                        "path": f"$.{key}",
                        "message": (
                            "This local review runs as a panel: findings, checks, assessment, "
                            "verdict, and answers belong to the arbitrator; import them with "
                            "record-arbitration"
                        ),
                    }
                )
    for key, value in user_input.items():
        field = f"$.{key}"
        schema = properties.get(key)
        if schema is None or key not in _LOCAL_SECTIONS:
            issues.append(
                {
                    "path": field,
                    "message": f"Unknown section; allowed sections are {', '.join(_LOCAL_SECTIONS)}",
                }
            )
            continue
        section_issues = schema_issues(schema, value, field, contract.artifact_schema())
        issues.extend(section_issues)
        # Shape must pass before any list is iterated or any entry field is read.
        if not section_issues:
            valid_sections.append((key, value))
    if issues:
        return {
            "status": "invalid",
            "draft_path": draft_path,
            "errors": issues,
            "note": (
                "Nothing was applied and the local draft is unchanged. Fix the named fields in "
                "the input file and run record-input again."
            ),
            "external_mutations": False,
        }
    draft_next = copy.deepcopy(selected_draft)
    applied: dict[str, Any] = {}
    for key, value in valid_sections:
        if key == "findings":
            draft_next["findings"] = draft_module.upsert_by_identity(
                cast("list[dict[str, Any]]", draft_next.get("findings") or []),
                cast("list[dict[str, Any]]", value),
                lambda item: str(item["id"]),
            )
        elif key == "checks":
            draft_next["checks"] = draft_module.upsert_by_identity(
                cast("list[dict[str, Any]]", draft_next.get("checks") or []),
                cast("list[dict[str, Any]]", value),
                lambda item: str(item["name"]),
            )
        elif key in {"question_answers", "question_verifications"}:
            draft_next[key] = _merge_result_entries(
                cast("list[dict[str, Any]]", draft_next.get(key) or []),
                cast("list[dict[str, Any]]", value),
                key,
                issues,
            )
        else:
            draft_next[key] = value
        applied[key] = len(value) if isinstance(value, list) else value
    if issues:
        return {
            "status": "invalid",
            "draft_path": draft_path,
            "errors": issues,
            "note": (
                "Nothing was applied and the local draft is unchanged. Fix the named fields in "
                "the input file and run record-input again."
            ),
            "external_mutations": False,
        }
    persist_local_draft(root, digest_value, selection, draft_next)
    return {
        "status": "ok",
        "draft_path": draft_path,
        "applied": applied,
        "pending": _local_gaps(draft_next),
        "next_action": context.runner_action(
            "finalize-local", "--bundle", bundle_path, "--report", draft_path
        ),
        "external_mutations": False,
    }


def record_local_participants(bundle_path: str, input_path: str) -> dict[str, Any]:
    bundle, digest_value = _snapshot_envelope(bundle_path)
    root = str(bundle["artifact_root"])
    _canonical_snapshot_check(bundle_path, root, digest_value, "participant selection requires")
    user_input = contract.read_json(
        contract.regular_file(Path(input_path), "participant selection"), "participant selection"
    )
    contract.reject_envelope_wrapper(user_input, "participant selection")
    selection = select_local_draft(root, bundle, digest_value)
    selected_draft = cast("dict[str, Any]", selection["draft"])
    if str(selected_draft.get("mode")) not in {"full", "incremental"}:
        raise contract.WorkflowError(
            "record-participants applies to full and incremental local reviews; unchanged "
            "local evidence needs no panel"
        )
    if len(cast("list[dict[str, Any]]", selected_draft.get("critics") or [])) > 0:
        raise contract.WorkflowError(
            "Participants are fixed once critic receipts exist; prepare the snapshot again to "
            "select a new panel"
        )
    if isinstance(selected_draft.get("arbitration"), dict):
        raise contract.WorkflowError(
            "An arbitration receipt is already recorded; prepare the snapshot again to select "
            "a new panel"
        )
    errors = draft_module.participant_selection_issues(user_input)
    if errors:
        return {
            "status": "invalid",
            "draft_path": f"{root}/local-review-draft.json",
            "errors": errors,
            "note": "The selection was not recorded and the local draft is unchanged.",
            "external_mutations": False,
        }
    selected_draft["participants"] = copy.deepcopy(user_input)
    selected_draft["critic_count"] = len(
        cast("list[dict[str, Any]]", user_input.get("critics") or [])
    )
    selected_draft["critics"] = []
    persist_local_draft(root, digest_value, selection, selected_draft)
    package_recorded = isinstance(selected_draft.get("context_package"), dict)
    return {
        "status": "ok",
        "draft_path": f"{root}/local-review-draft.json",
        "participants": selected_draft["participants"],
        "critic_count": selected_draft["critic_count"],
        **(
            {"critic_tasks": _panel_critic_tasks(selected_draft, bundle_path)}
            if package_recorded
            else {
                "critic_tasks_hint": (
                    "Record the context package next; its response returns one ready critic "
                    "task per selected participant"
                )
            }
        ),
        "arbitrator_task_hint": (
            "After every critic receipt is imported, the record-critic response returns the "
            "ready local arbitrator task"
        ),
        "external_mutations": False,
    }


def record_local_critic(
    bundle_path: str, input_path: str, participant: str | None = None
) -> dict[str, Any]:
    bundle, digest_value = _snapshot_envelope(bundle_path)
    root = str(bundle["artifact_root"])
    _canonical_snapshot_check(bundle_path, root, digest_value, "record-critic requires")
    user_input = contract.read_json(
        contract.regular_file(Path(input_path), "local critic receipt input"),
        "local critic receipt input",
    )
    contract.reject_envelope_wrapper(user_input, "local critic receipt input")
    selection = select_local_draft(root, bundle, digest_value)
    selected_draft = cast("dict[str, Any]", selection["draft"])
    if not isinstance(selected_draft.get("participants"), dict):
        raise contract.WorkflowError(
            "record-critic requires a recorded panel; run record-participants first"
        )
    critics = cast(
        "list[dict[str, Any]]", cast("dict[str, Any]", selected_draft["participants"])["critics"]
    )
    errors: list[dict[str, str]] = list(
        schema_issues(_LOCAL_CRITIC_RECEIPT_SCHEMA, user_input, "$", contract.artifact_schema())
    )
    if not errors:
        for field in ("run_id", "session_id"):
            if not isinstance(user_input.get(field), str) or user_input[field] == "":
                errors.append(
                    {
                        "path": f"$.{field}",
                        "message": (
                            f"Expected the critic's real native {field} identity; a fabricated "
                            "identity is rejected"
                        ),
                    }
                )
        if user_input.get("evidence_digest") != selected_draft.get("evidence_digest"):
            errors.append(
                {
                    "path": "$.evidence_digest",
                    "message": (
                        f"The receipt binds different evidence; this snapshot requires "
                        f"{selected_draft.get('evidence_digest')}. Do not rebind the receipt"
                    ),
                }
            )
    selected: dict[str, Any] | None = None
    if participant is None:
        errors.append(
            {
                "path": "$.participant",
                "message": (
                    "This local review runs as a panel; pass --participant with the selected "
                    "critic name so the receipt is bound to its participant"
                ),
            }
        )
    else:
        selected = next((item for item in critics if str(item["name"]) == participant), None)
        if selected is None:
            errors.append(
                {
                    "path": "$.participant",
                    "message": (
                        f"Unknown participant {participant}; the selected critics are "
                        + ", ".join(str(item["name"]) for item in critics)
                    ),
                }
            )
        elif isinstance(selected.get("receipt"), dict):
            errors.append(
                {
                    "path": "$.participant",
                    "message": (
                        f"Participant {participant} already has an imported receipt; each selected "
                        "critic is imported exactly once"
                    ),
                }
            )
        elif any(
            isinstance(item.get("receipt"), dict)
            and (
                str(item["receipt"]["run_id"]) == str(user_input.get("run_id"))
                or str(item["receipt"]["session_id"]) == str(user_input.get("session_id"))
            )
            for item in critics
        ):
            errors.append(
                {
                    "path": "$.participant",
                    "message": (
                        f"This receipt identity is already bound to another selected critic; "
                        f"participant {participant} needs its own subagent run"
                    ),
                }
            )
    if not errors and isinstance(selected_draft.get("context_package"), dict):
        _, package_payload = contract.artifact_payload(
            Path(str(cast("dict[str, Any]", selected_draft["context_package"])["path"])),
            "context_package",
        )
        versions = question_context_versions(package_payload)
        for index, item in enumerate(
            cast("list[dict[str, Any]]", user_input.get("question_answers") or [])
        ):
            if not isinstance(item, dict):
                continue
            question_id = str(item["question_id"])
            if question_id not in versions:
                errors.append(
                    {
                        "path": f"$.question_answers[{index}].question_id",
                        "message": (
                            f"Unknown question {question_id}; the recorded package contains "
                            f"questions {', '.join(versions) or 'none'}"
                        ),
                    }
                )
            elif not is_current_result(item, versions):
                errors.append(
                    {
                        "path": f"$.question_answers[{index}].context_digest",
                        "message": (
                            f"Stale answer: it binds context version {item.get('context_digest')} "
                            f"but the current package version of question {question_id} is "
                            f"{versions.get(question_id)}"
                        ),
                    }
                )
    if not errors:
        known = {
            str(item["id"])
            for item in cast("list[dict[str, Any]]", selected_draft.get("findings") or [])
        } | {
            str(finding["id"])
            for receipt in cast("list[dict[str, Any]]", selected_draft.get("critics") or [])
            for finding in cast("list[dict[str, Any]]", receipt.get("findings") or [])
        }
        for index, item in enumerate(
            cast("list[dict[str, Any]]", user_input.get("findings") or [])
        ):
            if isinstance(item, dict) and str(item["id"]) in known:
                errors.append(
                    {
                        "path": f"$.findings[{index}].id",
                        "message": (
                            f"Finding id {item['id']} already exists in this review; use a distinct id"
                        ),
                    }
                )
    if errors:
        return {
            "status": "invalid",
            "draft_path": f"{root}/local-review-draft.json",
            "errors": errors,
            "note": "The receipt was not imported and the local draft is unchanged.",
            "external_mutations": False,
        }
    if selected is not None:
        selected["receipt"] = {
            "run_id": str(user_input["run_id"]),
            "session_id": str(user_input["session_id"]),
        }
    selected_draft["critics"] = [
        *cast("list[dict[str, Any]]", selected_draft.get("critics") or []),
        copy.deepcopy(user_input),
    ]
    persist_local_draft(root, digest_value, selection, selected_draft)
    arbitrator_task = (
        _sync_local_arbitration_input(selected_draft, root, bundle_path)
        if not isinstance(selected_draft.get("arbitration"), dict)
        and _panel_complete(selected_draft)
        else None
    )
    return {
        "status": "ok",
        "draft_path": f"{root}/local-review-draft.json",
        "imported": {
            "findings": len(cast("list[dict[str, Any]]", user_input.get("findings") or [])),
            "answers": len(cast("list[dict[str, Any]]", user_input.get("question_answers") or [])),
        },
        "critics_recorded": len(cast("list[dict[str, Any]]", selected_draft["critics"])),
        **({"arbitrator_task": arbitrator_task} if arbitrator_task is not None else {}),
        "next_action": context.runner_action(
            "record-arbitration", "--bundle", bundle_path, "--input", "<file>"
        ),
        "external_mutations": False,
    }


def record_local_arbitration(bundle_path: str, input_path: str) -> dict[str, Any]:
    bundle, digest_value = _snapshot_envelope(bundle_path)
    root = str(bundle["artifact_root"])
    _canonical_snapshot_check(bundle_path, root, digest_value, "record-arbitration requires")
    user_input = contract.read_json(
        contract.regular_file(Path(input_path), "local arbitration receipt input"),
        "local arbitration receipt input",
    )
    contract.reject_envelope_wrapper(user_input, "local arbitration receipt input")
    selection = select_local_draft(root, bundle, digest_value)
    selected_draft = cast("dict[str, Any]", selection["draft"])
    if not isinstance(selected_draft.get("participants"), dict):
        raise contract.WorkflowError(
            "record-arbitration requires a recorded panel; run record-participants first"
        )
    if not _panel_complete(selected_draft):
        raise contract.WorkflowError(
            "Every selected critic receipt must be imported and bound before arbitration"
        )
    if isinstance(selected_draft.get("arbitration"), dict):
        raise contract.WorkflowError(
            "An arbitration receipt is already recorded; prepare the snapshot again to change "
            "decisions"
        )
    errors: list[dict[str, str]] = list(
        schema_issues(_LOCAL_ARBITRATION_SCHEMA, user_input, "$", contract.artifact_schema())
    )
    if not errors:
        for field in ("run_id", "session_id"):
            if not isinstance(user_input.get(field), str) or user_input[field] == "":
                errors.append(
                    {
                        "path": f"$.{field}",
                        "message": (
                            f"Expected the arbitrator's real native {field} identity; a fabricated "
                            "identity is rejected"
                        ),
                    }
                )
        if user_input.get("evidence_digest") != selected_draft.get("evidence_digest"):
            errors.append(
                {
                    "path": "$.evidence_digest",
                    "message": (
                        f"The receipt binds different evidence; this snapshot requires "
                        f"{selected_draft.get('evidence_digest')}. Do not rebind the receipt"
                    ),
                }
            )
        identities = {
            str(value)
            for item in cast("list[dict[str, Any]]", selected_draft.get("critics") or [])
            for value in (item.get("run_id"), item.get("session_id"))
        }
        if (
            str(user_input.get("run_id")) in identities
            or str(user_input.get("session_id")) in identities
        ):
            errors.append(
                {
                    "path": "$.session_id",
                    "message": "The arbitrator identity must differ from every critic",
                }
            )
    if not errors:
        # Coverage: one verdict per critic finding and per new arbitrator finding.
        # A merged finding may carry an accepted critic finding's id forward; the
        # report keeps stable IDs that way.
        critic_ids: set[str] = set()
        for receipt in cast("list[dict[str, Any]]", selected_draft.get("critics") or []):
            for item in cast("list[dict[str, Any]]", receipt.get("findings") or []):
                if str(item["id"]) in critic_ids:
                    errors.append(
                        {
                            "path": "$.dispositions",
                            "message": (
                                f"Finding id {item['id']} appears in more than one critic receipt; "
                                "use distinct ids"
                            ),
                        }
                    )
                critic_ids.add(str(item["id"]))
        dispositions = cast("list[dict[str, Any]]", user_input.get("dispositions") or [])
        accepted = {str(item["id"]) for item in dispositions if item.get("decision") == "accept"}
        merged_ids: list[str] = []
        for item in cast("list[dict[str, Any]]", user_input.get("findings") or []):
            item_id = str(item["id"])
            if item_id in merged_ids:
                errors.append(
                    {
                        "path": "$.findings",
                        "message": (
                            f"Duplicate merged finding id {item_id}; each report finding needs a "
                            "distinct id"
                        ),
                    }
                )
            if item_id in critic_ids and item_id not in accepted:
                errors.append(
                    {
                        "path": "$.findings",
                        "message": (
                            f"Finding id {item_id} is a rejected critic finding; a merged report "
                            "finding cannot carry it forward"
                        ),
                    }
                )
            merged_ids.append(item_id)
        candidates = critic_ids | {item for item in merged_ids if item not in critic_ids}
        verdict_ids = [str(item["id"]) for item in dispositions]
        missing = [item for item in candidates if item not in verdict_ids]
        unknown = [item for item in verdict_ids if item not in candidates]
        if len(set(verdict_ids)) != len(verdict_ids):
            errors.append(
                {
                    "path": "$.dispositions",
                    "message": (
                        "Each candidate finding receives exactly one verdict; duplicate disposition "
                        "ids are rejected"
                    ),
                }
            )
        if missing:
            errors.append(
                {
                    "path": "$.dispositions",
                    "message": f"No verdict for finding ids {', '.join(missing)}",
                }
            )
        if unknown:
            errors.append(
                {
                    "path": "$.dispositions",
                    "message": f"Dispositions name unknown finding ids {', '.join(unknown)}",
                }
            )
        for index, item in enumerate(dispositions):
            if "duplicate_of" in item and (
                item.get("decision") != "reject"
                or str(item["duplicate_of"]) not in accepted
                or str(item["duplicate_of"]) == str(item["id"])
            ):
                errors.append(
                    {
                        "path": f"$.dispositions[{index}].duplicate_of",
                        "message": "duplicate_of must name an accepted canonical finding",
                    }
                )
        derived = _expected_local_verdict(
            cast("list[dict[str, Any]]", user_input.get("findings") or []),
            cast("list[dict[str, Any]]", user_input.get("checks") or []),
        )
        if user_input.get("verdict") != derived:
            errors.append(
                {
                    "path": "$.verdict",
                    "message": f"The verdict must be {derived} for the recorded findings and checks",
                }
            )
    if not errors and isinstance(selected_draft.get("context_package"), dict):
        _, package_payload = contract.artifact_payload(
            Path(str(cast("dict[str, Any]", selected_draft["context_package"])["path"])),
            "context_package",
        )
        versions = question_context_versions(package_payload)
        question_ids = {
            str(item["id"])
            for item in cast("list[dict[str, Any]]", package_payload.get("questions") or [])
        }
        answers, contradictions = collect_answers(
            cast("list[dict[str, Any]]", selected_draft.get("critics") or [])
        )
        try:
            validate_verifications(
                cast("list[dict[str, Any]]", user_input.get("question_verifications") or []),
                question_ids,
                versions,
                answers,
            )
        except contract.WorkflowError as error:
            errors.append({"path": "$.question_verifications", "message": str(error)})
        resolved = {
            str(item["question_id"])
            for item in cast("list[dict[str, Any]]", user_input.get("question_verifications") or [])
        }
        unresolved = [item for item in contradictions if item not in resolved]
        if unresolved:
            errors.append(
                {
                    "path": "$.question_verifications",
                    "message": (
                        f"Critics disagree on {', '.join(unresolved)}; the arbitrator must resolve "
                        "every contradiction with one targeted question_verifications entry each"
                    ),
                }
            )
    if errors:
        return {
            "status": "invalid",
            "draft_path": f"{root}/local-review-draft.json",
            "errors": errors,
            "note": "The arbitration receipt was not imported and the local draft is unchanged.",
            "external_mutations": False,
        }
    draft_next = copy.deepcopy(selected_draft)
    draft_next["findings"] = copy.deepcopy(user_input["findings"])
    draft_next["checks"] = copy.deepcopy(user_input["checks"])
    draft_next["assessment"] = user_input["assessment"]
    draft_next["verdict"] = user_input["verdict"]
    merge_issues: list[dict[str, str]] = []
    draft_next["question_verifications"] = _merge_result_entries(
        cast("list[dict[str, Any]]", draft_next.get("question_verifications") or []),
        cast("list[dict[str, Any]]", user_input.get("question_verifications") or []),
        "question_verifications",
        merge_issues,
    )
    draft_next["arbitration"] = copy.deepcopy(user_input)
    persist_local_draft(root, digest_value, selection, draft_next)
    return {
        "status": "ok",
        "draft_path": f"{root}/local-review-draft.json",
        "imported": {
            "merged_findings": len(cast("list[dict[str, Any]]", user_input.get("findings") or [])),
            "verdicts": len(cast("list[dict[str, Any]]", user_input.get("dispositions") or [])),
        },
        "next_action": context.runner_action(
            "finalize-local",
            "--bundle",
            bundle_path,
            "--report",
            f"{root}/local-review-draft.json",
        ),
        "external_mutations": False,
    }


# Local counterpart of the draft package guard: re-recording a canonically
# changed package moves the report's answers and verifications collected for
# the previous questions into the report's historical section so that
# finalization cannot count them against the current questions. Exactly the
# entries selected by their own binding move; fresh results for the same
# question stay in place.
def _retire_superseded_results(
    report: dict[str, Any], pointer: dict[str, Any] | None, user_input: dict[str, Any]
) -> list[str]:
    previous: dict[str, Any] | None = None
    if pointer is not None:
        try:
            _, payload = contract.artifact_payload(
                Path(str(pointer["package_path"])), "context_package"
            )
            previous = {"payload": payload, "digest": str(pointer["package_digest"])}
        except contract.WorkflowError:
            pass
    answers = cast("list[dict[str, Any]]", report.get("question_answers") or [])
    verifications = cast("list[dict[str, Any]]", report.get("question_verifications") or [])
    superseded = extract_superseded_results(previous, user_input, answers, verifications)
    if superseded is None:
        return []
    versions = question_context_versions(user_input)

    def current(item: dict[str, Any]) -> bool:
        return is_current_result(item, versions)

    report["question_answers"] = [item for item in answers if current(item)]
    report["question_verifications"] = [item for item in verifications if current(item)]
    report["superseded_question_results"] = [
        *cast("list[dict[str, Any]]", report.get("superseded_question_results") or []),
        superseded.entry,
    ]
    return superseded.question_ids


def _validate_local_package(
    report: dict[str, Any],
    root: str,
    bundle: dict[str, Any],
    digest_value: str,
) -> dict[str, Any]:
    binding = report.get("context_package")
    if (
        not isinstance(binding, dict)
        or not isinstance(binding.get("path"), str)
        or not contract.is_digest(binding.get("digest"))
    ):
        raise contract.WorkflowError(
            "local review must bind the recorded context package; complete the returned "
            "template and run record-package"
        )
    pointer = read_package_pointer(root)
    if (
        pointer is None
        or str(pointer["package_path"]) != str(Path(str(binding["path"])).resolve())
        or str(pointer["package_digest"]) != binding["digest"]
    ):
        raise contract.WorkflowError(
            "local review package binding does not match the recorded context package; run "
            "record-package again"
        )
    _, package_payload = contract.artifact_payload(Path(str(binding["path"])), "context_package")
    validate_package_payload(
        package_payload,
        ExpectedPackage(
            mode="local",
            evidence_digest=digest_value,
            artifact_root=root,
            repo_root=str(bundle["repo_root"]),
            head_sha=str(bundle["head_sha"]),
            ref=cast("str | None", _python_get(bundle, "ref")),
            sections=local_section_digests(bundle),
        ),
    )
    questions = cast("list[dict[str, Any]]", package_payload.get("questions") or [])
    question_ids = {str(item["id"]) for item in questions}
    versions = question_context_versions(package_payload)
    answers = cast("list[dict[str, Any]]", report.get("question_answers") or [])
    validate_answers(answers, question_ids, versions, "$.question_answers")
    verifications = cast("list[dict[str, Any]]", report.get("question_verifications") or [])
    validate_verifications(verifications, question_ids, versions, answers)
    answered = {str(item["question_id"]) for item in answers}

    def covered(question_id: str) -> bool:
        return question_id in answered or any(
            str(item["question_id"]) == question_id for item in verifications
        )

    for entry in cast("list[dict[str, Any]]", report.get("superseded_question_results") or []):
        for answer in cast("list[dict[str, Any]]", entry.get("answers") or []):
            question_id = str(answer["question_id"])
            if question_id in question_ids and not covered(question_id):
                raise contract.WorkflowError(
                    f"question {question_id} was answered against a superseded context package "
                    f"(context digest {entry['context_digest']}); the current package changed "
                    "it, so it needs a fresh critic answer or primary verification"
                )
    for question in questions:
        if question.get("critic") is not True:
            continue
        question_id = str(question["id"])
        if not covered(question_id):
            raise contract.WorkflowError(
                f"question {question_id} is assigned to critics but no critic answer or primary "
                "verification covers it"
            )
    for answer in answers:
        if answer.get("verdict") != "not_verified":
            continue
        preserved = any(
            str(item["question_id"]) == str(answer["question_id"])
            and isinstance(item.get("original"), dict)
            and str(item["original"]["run_id"]) == str(answer.get("run_id"))
            and str(item["original"]["session_id"]) == str(answer.get("session_id"))
            for item in verifications
        )
        if not preserved:
            raise contract.WorkflowError(
                f"critic answer for {answer['question_id']} is not_verified; add one "
                "question_verifications entry that preserves the original answer"
            )
    return question_report(questions, answers, verifications)


def record_review(root: str, bundle_path: str, report_path: str) -> dict[str, Any]:
    bundle, digest_value = _snapshot_envelope(bundle_path)
    if str(Path(bundle_path).resolve()) != (
        f"{root}/artifacts/local_wip_snapshot/{digest_value}.json"
    ):
        raise contract.WorkflowError("local review requires its canonical immutable snapshot")
    local_draft = contract.read_json(Path(report_path), "local review draft")
    report = local_draft
    # A local panel review finalizes only after arbitration. The report
    # artifact stays schema-identical: receipt answers and the arbitrator's
    # verifications merge in as coverage evidence, while the receipts, the
    # selection, and the arbitration receipt itself are preserved verbatim as
    # companions under local-panel/.
    panel: dict[str, Any] | None = None
    if isinstance(local_draft.get("participants"), dict):
        if not _panel_complete(local_draft):
            raise contract.WorkflowError(
                "Every selected local critic receipt must be imported and bound before finalization"
            )
        if not isinstance(local_draft.get("arbitration"), dict):
            raise contract.WorkflowError(
                "A local panel review requires the arbitration receipt; import it with "
                "record-arbitration before finalization"
            )
        panel = {
            "participants": local_draft["participants"],
            "critics": local_draft["critics"],
            "arbitration": local_draft["arbitration"],
        }
        report = {
            **{
                key: value
                for key, value in local_draft.items()
                if key not in {"participants", "critics", "arbitration", "critic_count"}
            },
            "question_answers": collect_answers(
                cast("list[dict[str, Any]]", local_draft["critics"])
            )[0],
            "question_verifications": copy.deepcopy(
                cast("dict[str, Any]", local_draft["arbitration"]).get("question_verifications")
                or []
            ),
        }
    validate_report(report)
    if report["evidence_digest"] != digest_value:
        raise contract.WorkflowError("local review does not bind the current snapshot")
    followup = prepare_followup(
        root,
        bundle,
        digest_value,
        "off" if report["mode"] == "full" else "auto",
    )
    if report["previous_review_digest"] != followup["previous_review_digest"]:
        raise contract.WorkflowError("local review baseline changed; prepare again")
    if report["mode"] != followup["mode"]:
        raise contract.WorkflowError("local review mode does not match the available baseline")
    if followup["baseline_compatible"] is True:
        _validate_continuity(report, cast("dict[str, Any]", followup["previous_report"]))
    question_summary = _validate_local_package(report, root, bundle, digest_value)
    if finalize_local(bundle_path)["status"] != "ok":
        raise contract.WorkflowError("local evidence changed before report finalization")
    if panel is not None:
        directory = contract.private_directory(Path(root) / LOCAL_PANEL_DIR)
        suffix = digest_value[:16]
        contract.write_json(directory / f"participants-{suffix}.json", panel["participants"])
        contract.write_json(directory / f"critics-{suffix}.json", panel["critics"])
        contract.write_json(directory / f"arbitration-{suffix}.json", panel["arbitration"])
    path, report_digest = contract.write_artifact(Path(root), "local_review_report", report)
    contract.write_json(Path(root) / "local-review.json", {"review_digest": report_digest})
    return {
        "artifact_path": str(path),
        "digest": report_digest,
        "mode": report["mode"],
        "verdict": report["verdict"],
        "question_summary": question_summary,
    }
