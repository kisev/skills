"""The run's decision-driven tail; canonical artifacts remain unchanged."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

from reviewmatic import context, render, review_worktree, run_panel
from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract, review_semver

NAME = "run-authoring.json"


def load(root: Path) -> dict[str, Any] | None:
    path = root / NAME
    return (
        contract.read_json(contract.regular_file(path, "run authoring"), "run authoring")
        if path.exists()
        else None
    )


def save(root: Path, state: dict[str, Any]) -> None:
    contract.write_json(root / NAME, state)


def selected(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    progress = context.load_progress(root)
    if progress is None:
        raise contract.WorkflowError("the run tail requires review progress")
    artifact = context.progress_artifact(root, progress, "context", "review_context")
    if artifact is None:
        raise contract.WorkflowError("the run tail requires complete selected context")
    _, evidence = context.review_evidence_from_root(root)
    return progress, artifact[1], evidence


def remember_intents(root: Path, decision_digest: str, intents: list[dict[str, Any]]) -> None:
    save(root, {"decision_digest": decision_digest, "intents": copy.deepcopy(intents)})


def adopt_draft(
    root: Path,
    draft: dict[str, Any],
    compiled: dict[str, Any],
    progress: dict[str, Any],
    review_context: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    """Checkpoint a validated draft into the same tail used by run."""
    historical_path = root / "review-drafts" / f"draft-authorship-{contract.digest(draft)}.json"
    contract.write_json(historical_path, copy.deepcopy(draft))
    finalize_path, finalize_digest = contract.write_artifact(
        root,
        "finalize_report",
        {
            "status": "ok",
            "changed": [],
            "complete": True,
            "evidence_digest": draft["evidence_digest"],
            "evidence_kind": "evidence_snapshot",
            "evidence_fingerprint_digest": contract.digest(contract.fingerprint(evidence)),
            "head_sha": evidence["head_sha"],
            "external_mutations": False,
        },
    )
    receipt = compiled.get("receipt")
    receipt_path, receipt_digest = (
        contract.write_artifact(root, "critic_receipt", receipt)
        if receipt is not None
        else (None, None)
    )
    decision = {
        **compiled["decision"],
        "finalize_digest": finalize_digest,
        "critic_receipt_digest": receipt_digest,
    }
    decision_path, decision_digest = contract.write_artifact(root, "review_decision", decision)
    intents = [
        {
            "finding_id": row["id"],
            "publication": copy.deepcopy(row["publication"]),
            "dependencies": copy.deepcopy(row["dependencies"]),
        }
        for row in draft["dispositions"]
        if row["decision"] == "accept" and "publication" in row
    ]
    prose_path = render.prose_file(root, decision_digest)
    prose = render.prose_projection(compiled["content"], review_context, evidence)
    contract.write_json(prose_path, prose)
    state = {
        "decision_digest": decision_digest,
        "intents": intents,
        "content": copy.deepcopy(compiled["content"]),
        "prose": prose,
        "prose_path": str(prose_path),
        "applied": True,
        "draft_authorship": str(historical_path),
    }
    if "participants" in draft:
        run_panel.write(
            root,
            {
                "schema": run_panel.PANEL_SCHEMA,
                "participants": copy.deepcopy(draft["participants"]),
                "receipts": copy.deepcopy(draft["critics"]),
            },
        )
    save(root, state)
    context.advance_progress(
        root,
        "content_missing",
        critic_receipt_path=str(receipt_path) if receipt_path else None,
        critic_receipt_digest=receipt_digest,
        finalize_report_path=str(finalize_path),
        finalize_report_digest=finalize_digest,
        decision_path=str(decision_path),
        decision_digest=decision_digest,
        plan_path=None,
        plan_digest=None,
    )


def content_from_decision(
    decision: dict[str, Any],
    review_context: dict[str, Any],
    evidence: dict[str, Any],
    intents: list[dict[str, Any]],
    authored: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Use the same renderer for the draft and the real run."""
    by_id = {str(row["finding_id"]): row for row in intents}
    accepted = decision.get("accepted_findings") or []
    dummy: dict[str, Any] = {
        "findings": accepted,
        "dispositions": [
            {
                "id": finding["id"],
                "decision": "accept",
                "reason": "Recorded decision.",
                "publication": by_id.get(str(finding["id"]), {}).get("publication"),
                "dependencies": by_id.get(str(finding["id"]), {}).get(
                    "dependencies",
                    {
                        "paths": review_context["exact_git"].get("changed_paths", []),
                        "thread_ids": [],
                        "ci": False,
                        "metadata_fields": [],
                    },
                ),
            }
            for finding in accepted
        ],
        "content": {"locale": (authored or {}).get("locale", "en")},
    }
    missing = [finding for finding in accepted if str(finding["id"]) not in by_id]
    if missing:
        # Missing semantic intent is a prose stop, not a guess at a publication.
        content = context.content_template(
            evidence, review_context, decision, dummy["content"]["locale"]
        )
        content["semver_assessment"] = review_semver.rendered_template(evidence, review_context)
        content["finding_publications"] = []
    else:
        content = render.render_content(dummy, review_context, evidence)
    if authored:
        previous_semver = authored.get("semver_assessment") or {}
        previous_basis = previous_semver.get("baseline")
        if isinstance(previous_basis, dict):
            content["semver_assessment"] = review_semver.rendered_template(
                evidence, review_context, {key: previous_basis[key] for key in ("name", "source")}
            )
        elif previous_semver.get("mode") == "target_fallback":
            content["semver_assessment"] = review_semver.template(evidence, review_context)
        for key, value in authored.items():
            if key in render.PROSE_KEYS and key not in {
                "finding_publications",
                "previous_finding_assessments",
            }:
                if key == "semver_assessment":
                    content[key].update(
                        {
                            field: copy.deepcopy(value[field])
                            for field in render.SEMVER_PROSE_KEYS
                            if field in value
                        }
                    )
                else:
                    content[key] = copy.deepcopy(value)
        old_rows = {str(row["finding_id"]): row for row in authored.get("finding_publications", [])}
        for row in content["finding_publications"]:
            old = old_rows.get(str(row["finding_id"]))
            if old:
                row.update(
                    {
                        key: copy.deepcopy(old[key])
                        for key in (
                            "body",
                            "patch",
                            "patch_reason",
                            "split_rationale",
                            "suggestions",
                        )
                        if key in old
                    }
                )
    content["findings"] = copy.deepcopy(accepted)
    content["rejected_candidates"] = render.rejected_from_decision(
        decision, intents, review_context
    )
    presented = cast(
        "dict[str, Any]", render.copied_presentation(content, evidence, review_context)
    )
    presented["findings"] = copy.deepcopy(accepted)
    presented["rejected_candidates"] = copy.deepcopy(content["rejected_candidates"])
    return presented


def prepare(root: Path) -> dict[str, Any]:
    progress, review_context, evidence = selected(root)
    decision_artifact = context.progress_artifact(root, progress, "decision", "review_decision")
    if decision_artifact is None:
        raise contract.WorkflowError("the prose tail requires the recorded decision")
    decision = decision_artifact[1]
    state = load(root)
    if state is None or state.get("decision_digest") != progress["decision_digest"]:
        state = {"decision_digest": progress["decision_digest"], "intents": []}
    if "content" not in state:
        state["content"] = content_from_decision(
            decision, review_context, evidence, state["intents"]
        )
        state["content"]["locale"] = progress["locale"]
        state["applied"] = False
        path = render.prose_file(root, str(progress["decision_digest"]))
        prose = render.prose_projection(state["content"], review_context, evidence)
        existing = {str(row["finding_id"]) for row in state["intents"]}
        for finding in decision.get("accepted_findings", []):
            if str(finding["id"]) not in existing:
                prose["finding_publications"].append(
                    {
                        "finding_id": finding["id"],
                        "publication": {
                            "kind": "<KIND: line, general, local_fix, existing_thread>",
                            "fix_mode": "<FIX_MODE: suggestion or patch>",
                        },
                        "body": "<BODY: publication explanation>",
                    }
                )
        contract.write_json(path, prose)
        state["prose_path"] = str(path)
        save(root, state)
    return state


def record_prose(root: Path, input_path: str) -> dict[str, Any]:
    state = prepare(root)
    progress, review_context, evidence = selected(root)
    incoming = contract.read_json(
        contract.regular_file(Path(input_path), "content prose"), "content prose"
    )
    contract.reject_envelope_wrapper(incoming, "content prose")
    original_prose = copy.deepcopy(incoming)
    rows = incoming.get("finding_publications", [])
    known = {str(row["id"]) for row in state["content"]["findings"]}
    if not isinstance(rows, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("finding_id"), str)
        or row["finding_id"] not in known
        for row in rows
    ):
        raise contract.WorkflowError(
            "finding_publications[*].finding_id: return a prepared finding identifier unchanged; unknown or substituted identities are forbidden"
        )
    intents = {str(row["finding_id"]): copy.deepcopy(row) for row in state["intents"]}
    for row in incoming.get("finding_publications", []):
        publication = row.pop("publication", None)
        if publication is not None:
            if (
                not isinstance(publication, dict)
                or publication.get("kind")
                not in {"general", "line", "local_fix", "existing_thread"}
                or publication.get("fix_mode") not in {"patch", "suggestion"}
            ):
                raise contract.WorkflowError(
                    "publication intent requires kind general/line/local_fix/existing_thread and fix_mode patch/suggestion"
                )
            if isinstance(row.get("target"), dict):
                publication["target"] = copy.deepcopy(row["target"])
            intents[str(row["finding_id"])] = {
                "finding_id": row["finding_id"],
                "publication": publication,
            }
        elif isinstance(row.get("target"), dict) and str(row.get("finding_id")) in intents:
            intents[str(row["finding_id"])]["publication"]["target"] = copy.deepcopy(row["target"])
    artifact = context.progress_artifact(root, progress, "decision", "review_decision")
    if artifact is None:
        raise contract.WorkflowError("the run decision changed before prose application")
    content = content_from_decision(
        artifact[1], review_context, evidence, list(intents.values()), state["content"]
    )
    resolved = render.resolve_prose_fixes(content, incoming, review_context, evidence)
    content = render.apply_prose(content, resolved)
    content = render.reconcile_history(content, artifact[1], review_context)
    state.update(
        content=content,
        intents=list(intents.values()),
        prose=render.prose_projection(content, review_context, evidence),
        prose_input=original_prose,
        applied=True,
    )
    save(root, state)
    return {
        "status": "ok",
        "artifact_root": str(root),
        "prose_path": state["prose_path"],
        "fill_guidance": render.placeholder_guidance(content),
        "next_action": context.runner_action(
            "run", "--resume", "--url", str(evidence["target"]["url"])
        ),
        "external_mutations": False,
    }


def finalize(root: Path) -> dict[str, Any]:
    state = prepare(root)
    progress, _review_context, _evidence = selected(root)
    guidance = render.placeholder_guidance(state["content"])
    if not state.get("applied") or guidance:
        raise contract.WorkflowError(
            "fill the generated prose surface and apply it with record-prose before finalization"
        )
    return cast(
        "dict[str, Any]",
        context.scaffold_review(
            str(progress["evidence_path"]),
            str(progress["context_path"]),
            str(progress["decision_path"]),
            "",
            {
                "content": state["content"],
                "freshness_checked": True,
                "source": {"run_authoring": copy.deepcopy(state)},
            },
        ),
    )


def delta_scope(
    old: dict[str, Any],
    new: dict[str, Any],
    old_context: dict[str, Any],
    new_context: dict[str, Any],
) -> dict[str, Any]:
    repo = Path(str(new_context["exact_git"]["repo_root"]))
    paths = str(
        contract.git_read(
            repo, "diff", "--name-only", str(old["head_sha"]), str(new["head_sha"]), "--"
        )
    ).splitlines()
    old_threads = {str(row["root_note_id"]): row for row in old_context["discussions"]}
    threads = [
        str(row["root_note_id"])
        for row in new_context["discussions"]
        if str(row["root_note_id"]) not in old_threads
        or context.discussion_signature(row)
        != context.discussion_signature(old_threads[str(row["root_note_id"])])
    ]
    old_notes = {
        str(row["id"]): row for row in old_context.get("notes", []) if row.get("system") is not True
    }
    discussion_note_ids = {
        str(note["id"]) for thread in new_context["discussions"] for note in thread.get("notes", [])
    }
    notes = [
        str(row["id"])
        for row in new_context.get("notes", [])
        if row.get("system") is not True
        and str(row["id"]) not in discussion_note_ids
        and old_notes.get(str(row["id"])) != row
    ]
    ignored = {
        "sha",
        "diff_refs",
        "updated_at",
        "created_at",
        "pipeline",
        "head_pipeline",
        "latest_build_started_at",
        "latest_build_finished_at",
    }
    metadata = sorted(
        key
        for key in set(old["object"]) | set(new["object"])
        if key not in ignored and old["object"].get(key) != new["object"].get(key)
    )
    if old_context.get("release_evidence") != new_context.get("release_evidence"):
        metadata.append("release_evidence")
    if old.get("labels") != new.get("labels"):
        metadata.append("label_catalog")
    boundary_changed = any(old.get(key) != new.get(key) for key in ("base_sha", "start_sha"))
    if boundary_changed:
        metadata.append("comparison_boundary")
    return {
        "from_head": old["head_sha"],
        "to_head": new["head_sha"],
        "changed_paths": sorted(paths),
        "changed_thread_ids": sorted(threads),
        "changed_note_ids": sorted(notes),
        "metadata_fields": metadata,
        "pipelines_changed": old["pipelines"] != new["pipelines"],
        "comparison_boundary_changed": boundary_changed,
    }


def re_anchor(root: Path) -> dict[str, Any] | None:
    """Checkpoint authorship, collect new evidence, and ask for a fresh delta check."""
    state = load(root)
    if state is not None and state.get("pending_delta"):
        return state
    state = prepare(root)
    progress, old_context, old = selected(root)
    current = contract.collect(
        old["target"], "code-review", persist=False, locale=str(progress["locale"])
    )
    if current.get("retrieval_complete") is not True:
        raise contract.WorkflowError(
            "delta re-anchor requires complete current evidence; authorship unchanged"
        )
    fresh_old_context = (
        context.collect_context(
            cast("dict[str, Any]", current),
            str(progress["evidence_digest"]),
            str(progress["repo_root"]),
        )
        if current["head_sha"] == old["head_sha"]
        else None
    )
    if (
        contract.fingerprint(current) == contract.fingerprint(old)
        and fresh_old_context is not None
        and context.contexts_match(old_context, fresh_old_context)
    ):
        return None
    _, old_decision = contract.artifact_payload(
        Path(str(progress["decision_path"])), "review_decision"
    )
    history = {
        "progress": copy.deepcopy(progress),
        "decision": copy.deepcopy(old_decision),
        "authoring": copy.deepcopy(state),
        "panel": run_panel.load(root),
    }
    history_path = root / "review-drafts" / f"authorship-{contract.digest(history)}.json"
    contract.write_json(history_path, history)
    bundle = contract.collect(old["target"], "code-review", locale=str(progress["locale"]))
    if bundle.get("retrieval_complete") is not True:
        raise contract.WorkflowError(
            "delta re-anchor collection is incomplete; original authorship checkpoint retained"
        )
    repo = str(progress["repo_root"])
    if bundle["head_sha"] != old["head_sha"]:
        worktree = review_worktree.prepare_review_worktree(
            repo_root=repo,
            evidence=cast("dict[str, Any]", bundle),
            evidence_digest=str(bundle["preview_digest"]),
            supersede_root=str(root),
        )
        repo = str(worktree["path"])
    new_context = context.collect_context(
        cast("dict[str, Any]", bundle), str(bundle["preview_digest"]), repo, "auto"
    )
    if new_context.get("complete") is not True:
        raise contract.WorkflowError(
            "delta re-anchor context is incomplete; original authorship checkpoint retained"
        )
    if (
        new_context["current_user_id"] != old_context["current_user_id"]
        or new_context["role"] != old_context["role"]
    ):
        raise contract.WorkflowError(
            "delta re-anchor cannot carry authorship across a changed authenticated user or author/reviewer role"
        )
    context_path, context_digest = contract.write_artifact(root, "review_context", new_context)
    scope = delta_scope(old, cast("dict[str, Any]", bundle), old_context, new_context)
    new_mode = str(new_context["incremental"]["mode"])
    mode = new_mode if new_mode in {"incremental", "unchanged"} else str(progress["mode"])
    # A moved unfinished review still needs the separate delta check even when
    # its new head matches a previously finalized baseline.
    if mode == "unchanged":
        mode = "normal"
        new_context["incremental"]["mode"] = "full"
        context_path, context_digest = contract.write_artifact(root, "review_context", new_context)
    dependencies = {
        str(row["finding_id"]): row.get("dependencies") or {} for row in state["intents"]
    }
    targets = []
    if scope["from_head"] != scope["to_head"] or scope["comparison_boundary_changed"]:
        targets.append(
            {
                "id": "code_delta",
                "kind": "metadata",
                "conclusion": {
                    key: copy.deepcopy(state["content"].get(key))
                    for key in (
                        "summary",
                        "architecture_assessment",
                        "semver_impact",
                        "semver_rationale",
                    )
                },
            }
        )
    for finding in old_decision.get("accepted_findings", []):
        dep = dependencies.get(str(finding["id"])) or {
            "paths": old_context["exact_git"].get("changed_paths", []),
            "ci": False,
            "metadata_fields": scope["metadata_fields"],
        }
        if (
            scope["comparison_boundary_changed"]
            or set(dep.get("paths") or []) & set(scope["changed_paths"])
            or (dep.get("ci") and scope["pipelines_changed"])
            or set(dep.get("metadata_fields") or []) & set(scope["metadata_fields"])
            or set(dep.get("thread_ids") or []) & set(scope["changed_thread_ids"])
        ):
            targets.append(
                {
                    "id": finding["id"],
                    "kind": "finding",
                    "conclusion": copy.deepcopy(finding),
                    "dependencies": dep,
                }
            )
    if scope["changed_paths"] or scope["metadata_fields"]:
        for issue in state["content"].get("recommended_issues", []):
            targets.append({"id": issue["id"], "kind": "issue", "conclusion": copy.deepcopy(issue)})
    for identifier in scope["changed_thread_ids"]:
        targets.append(
            {
                "id": f"thread:{identifier}",
                "kind": "thread",
                "conclusion": next(
                    (
                        row
                        for row in state["content"]["thread_decisions"]
                        if str(row["id"]) == identifier
                    ),
                    {},
                ),
            }
        )
    if scope["metadata_fields"]:
        targets.append(
            {
                "id": "metadata",
                "kind": "metadata",
                "conclusion": {
                    "mr_metadata_assessment": state["content"].get("mr_metadata_assessment", {}),
                    "label_assessments": state["content"].get("label_assessments", []),
                    "semver_assessment": state["content"].get("semver_assessment", {}),
                },
            }
        )
    if scope["changed_note_ids"]:
        targets.append(
            {
                "id": "notes",
                "kind": "metadata",
                "conclusion": {"changed_note_ids": scope["changed_note_ids"]},
            }
        )
    if scope["pipelines_changed"]:
        targets.append(
            {"id": "ci", "kind": "ci", "conclusion": old_decision.get("ci_job_assessments", [])}
        )
    pending = {
        "history_path": str(history_path),
        "history_digest": contract.digest(history),
        "scope": scope,
        "scope_digest": contract.digest(scope),
        "targets": targets,
        "checked": False,
        "new_evidence_digest": bundle["preview_digest"],
        "new_context_digest": context_digest,
    }
    template: dict[str, Any] = {
        "schema": "code-review/delta-check/v1",
        "evidence_digest": bundle["preview_digest"],
        "scope_digest": pending["scope_digest"],
        "run_id": "",
        "session_id": "",
        "checks": [
            {
                "id": row["id"],
                "verdict": "not_verified",
                "evidence": "<EVIDENCE: verify the delta and this conclusion>",
            }
            for row in targets
        ],
        "new_findings": [],
        "new_dispositions": [],
        "external_mutations": False,
        "ci_job_assessments": context.ci_job_assessment_template(cast("dict[str, Any]", bundle)),
        "verifier": (history["panel"] or {}).get("participants", {}).get("arbitrator"),
        "inputs": {
            "evidence_path": bundle["preview_artifact_path"],
            "context_path": str(context_path),
            "repo_root": repo,
            "history_path": str(history_path),
        },
        "scope": scope,
    }
    for row in template["checks"]:
        target = next(item for item in targets if item["id"] == row["id"])
        row["resolution"] = None
        if target["kind"] == "finding":
            row["finding"] = copy.deepcopy(target["conclusion"])
        elif target["kind"] == "issue":
            row["issue"] = copy.deepcopy(target["conclusion"])
    template_path = root / "review-drafts" / f"delta-check-{context_digest[:16]}.json"
    contract.write_json(template_path, template)
    pending["template_path"] = str(template_path)
    state["pending_delta"] = pending
    state["history"] = [*state.get("history", []), str(history_path)]
    state["historical_heads"] = list(
        dict.fromkeys([*state.get("historical_heads", []), old["head_sha"]])
    )
    state["historical_refs"] = list(
        dict.fromkeys(
            [
                *state.get("historical_refs", []),
                *(sha for sha, _source in context.raw_ref_sources(old, old_context)),
            ]
        )
    )
    save(root, state)
    context.begin_review(
        str(bundle["preview_artifact_path"]),
        str(bundle["preview_digest"]),
        str(root),
        repo,
        "normal" if mode not in {"fast", "normal"} else mode,
        str(progress["locale"]),
        "auto",
    )
    context.advance_progress(
        root,
        "context_ready",
        context_path=str(context_path),
        context_digest=context_digest,
        mode=mode,
    )
    return state


def _validated_delta(
    root: Path, result: dict[str, Any], pending: dict[str, Any], progress: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (
        result.get("schema") != "code-review/delta-check/v1"
        or result.get("evidence_digest") != progress["evidence_digest"]
        or result.get("scope_digest") != pending["scope_digest"]
        or result.get("external_mutations") is not False
    ):
        raise contract.WorkflowError(
            "delta check must bind the new evidence and the exact pending delta; original receipt digests are never rewritten"
        )
    if not all(
        isinstance(result.get(key), str) and result[key] for key in ("run_id", "session_id")
    ):
        raise contract.WorkflowError("delta check requires real native run/session identities")
    history_path = Path(pending["history_path"])
    history = contract.read_json(
        contract.regular_file(history_path, "authorship history"), "authorship history"
    )
    if contract.digest(history) != pending["history_digest"]:
        raise contract.WorkflowError("authorship history digest changed")
    old_decision = history["decision"]
    if (
        result["run_id"] == old_decision["run_id"]
        or result["session_id"] == old_decision["session_id"]
    ):
        raise contract.WorkflowError("delta verifier must be a new independent native session")
    old_receipt = context.progress_artifact(
        root, history["progress"], "critic_receipt", "critic_receipt"
    )
    if old_receipt is not None:
        previous = [old_receipt[1], *old_receipt[1].get("contributors", [])]
        if any(
            result["run_id"] == row["run_id"] or result["session_id"] == row["session_id"]
            for row in previous
        ):
            raise contract.WorkflowError(
                "delta verifier identity must differ from the historical critic sessions"
            )
    verifier = (history["panel"] or {}).get("participants", {}).get("arbitrator")
    if result.get("verifier") != verifier:
        raise contract.WorkflowError(
            "delta check must name the selected verifier configuration; no silent model/profile substitution"
        )
    checks = result.get("checks")
    if not isinstance(checks, list) or any(not isinstance(row, dict) for row in checks):
        raise contract.WorkflowError("checks must be an array of per-conclusion verdicts")
    by_id = {str(row.get("id")): row for row in checks}
    if len(by_id) != len(checks) or set(by_id) != {str(row["id"]) for row in pending["targets"]}:
        raise contract.WorkflowError(
            "delta check must verdict every affected conclusion exactly once, without inventing targets"
        )
    if any(
        row.get("verdict") not in {"confirmed", "refuted", "changed", "not_verified"}
        or not isinstance(row.get("evidence"), str)
        or not row["evidence"]
        or str(row["evidence"]).startswith("<")
        for row in checks
    ):
        raise contract.WorkflowError(
            "each delta verdict needs confirmed/refuted/changed/not_verified and concrete verification evidence"
        )
    return history, checks


def record_delta(root: Path, input_path: str) -> dict[str, Any]:
    state = load(root)
    if state is None or not state.get("pending_delta"):
        raise contract.WorkflowError("no delta check is pending")
    pending = state["pending_delta"]
    result = contract.read_json(
        contract.regular_file(Path(input_path), "delta check"), "delta check"
    )
    progress, review_context, evidence = selected(root)
    history, checks = _validated_delta(root, result, pending, progress)
    old_decision = history["decision"]
    history_path = Path(pending["history_path"])
    check_path = root / "review-drafts" / f"delta-result-{contract.digest(result)}.json"
    contract.write_json(check_path, result)
    target_kinds = {str(row["id"]): str(row["kind"]) for row in pending["targets"]}
    unresolved = [
        row
        for row in checks
        if row["verdict"] == "not_verified"
        or (row["verdict"] == "refuted" and row.get("resolution") != "accept_refutation")
        or (row["verdict"] == "changed" and row.get("resolution") != "revise")
        or (
            row["verdict"] != "confirmed"
            and target_kinds[str(row["id"])] not in {"finding", "issue"}
            and not isinstance(row.get("prose"), dict)
        )
        or (
            target_kinds[str(row["id"])] == "thread"
            and not next(
                target["conclusion"] for target in pending["targets"] if target["id"] == row["id"]
            )
            and not isinstance(row.get("prose"), dict)
        )
    ]
    if unresolved:
        pending["result_path"] = str(check_path)
        pending["needs_addressed"] = copy.deepcopy(unresolved)
        save(root, state)
        return {
            "status": "needs_targeted_repair",
            "affected": [row["id"] for row in unresolved],
            "prose_path": state["prose_path"],
            "template_path": pending["template_path"],
            "note": "Address only these conclusions; the complete authored prose and historical checks are retained.",
            "external_mutations": False,
        }
    primary = [
        *copy.deepcopy(old_decision["findings"]),
        *copy.deepcopy(old_decision.get("critic_findings") or []),
    ]
    responses = copy.deepcopy(old_decision["responses"])
    revised_issues: dict[str, dict[str, Any]] = {}
    closed_issues: dict[str, str] = {}
    corrections: list[dict[str, Any]] = []
    for check in checks:
        kind = target_kinds[str(check["id"])]
        if (
            check["verdict"] != "confirmed" or isinstance(check.get("prose"), dict)
        ) and kind not in {"finding", "issue"}:
            correction = check.get("prose")
            allowed = (
                {"thread_decisions"}
                if kind == "thread"
                else {
                    "mr_metadata_assessment",
                    "summary",
                    "architecture_assessment",
                    "label_assessments",
                    "semver_assessment",
                    "semver_impact",
                    "semver_rationale",
                    "checks",
                    "chat_assessment",
                }
                if kind == "metadata"
                else {"checks", "chat_assessment"}
            )
            if not isinstance(correction, dict) or set(correction) - allowed:
                raise contract.WorkflowError(
                    f"addressed {kind} correction permits only {', '.join(sorted(allowed))}"
                )
            corrections.append(copy.deepcopy(correction))
            continue
        if check["verdict"] == "refuted":
            if check.get("resolution") != "accept_refutation":
                raise contract.WorkflowError(
                    "refuted conclusion needs the addressed accept_refutation decision"
                )
            if kind == "issue":
                closed_issues[str(check["id"])] = check["evidence"]
                continue
            for response in responses:
                if response["id"] == check["id"]:
                    response.update(decision="reject", reason=check["evidence"])
        elif check["verdict"] == "changed":
            if (
                next(row["kind"] for row in pending["targets"] if row["id"] == check["id"])
                == "issue"
            ):
                issue = check.get("issue")
                if not isinstance(issue, dict) or issue.get("id") != check["id"]:
                    raise contract.WorkflowError(
                        "changed follow-up needs its revised proposal with the stable id"
                    )
                context.validate_recommended_issues([issue])
                revised_issues[str(issue["id"])] = copy.deepcopy(issue)
                continue
            finding = check.get("finding")
            if (
                not isinstance(finding, dict)
                or finding.get("id") != check["id"]
                or not contract.detailed_findings_are_valid([finding])
            ):
                raise contract.WorkflowError(
                    "changed finding needs a complete verified finding with its stable id; other conclusion kinds need targeted prose repair"
                )
            primary = [
                copy.deepcopy(finding) if row["id"] == check["id"] else row for row in primary
            ]
    new_findings = result.get("new_findings") or []
    if not contract.detailed_findings_are_valid(new_findings):
        raise contract.WorkflowError("new delta findings require complete structured evidence")
    novel = result.get("new_dispositions") or []
    if not isinstance(novel, list) or any(not isinstance(row, dict) for row in novel):
        raise contract.WorkflowError(
            "new_dispositions must contain one semantic decision per new delta finding"
        )
    issues = draft_module.schema_issues(
        {"type": "array", "items": draft_module._DISPOSITION}, novel, "$.new_dispositions"
    )
    if issues:
        raise contract.WorkflowError(
            "new delta dispositions are invalid: "
            + "; ".join(f"{row['path']}: {row['message']}" for row in issues)
        )
    fresh_receipt = {
        "schema": "portable-gitlab/critic-receipt/v2",
        "evidence_digest": progress["evidence_digest"],
        "run_id": result["run_id"],
        "session_id": result["session_id"],
        "findings": new_findings,
        "external_mutations": False,
        "scope_digest": review_context["incremental"]["incremental_delta_digest"]
        if progress["mode"] == "incremental"
        else pending["scope_digest"],
        "target_finding_ids": [
            str(row["id"]) for row in pending["targets"] if row["kind"] in {"finding", "issue"}
        ],
    }
    # This is a new certificate over the delta plus explicitly carried history,
    # not an old receipt with a replacement evidence_digest.
    scope = (
        review_context["incremental"]["incremental_delta_digest"]
        if progress["mode"] == "incremental"
        else None
    )
    contract.validate_critic(fresh_receipt, str(progress["evidence_digest"]), scope)
    receipt_path, receipt_digest = contract.write_artifact(root, "critic_receipt", fresh_receipt)
    new_ids = {str(row["id"]) for row in new_findings}
    if new_ids & {str(row["id"]) for row in primary}:
        raise contract.WorkflowError(
            "new delta findings need distinct ids; revise an existing conclusion through checks instead"
        )
    if len(novel) != len(new_ids) or {str(row["id"]) for row in novel} != new_ids:
        pending["new_findings"] = new_findings
        pending["result_path"] = str(check_path)
        save(root, state)
        return {
            "status": "needs_targeted_repair",
            "affected": [row["id"] for row in new_findings],
            "prose_path": state["prose_path"],
            "note": "New delta findings need addressed dispositions; do not re-author the complete review.",
            "external_mutations": False,
        }
    responses.extend(
        {
            key: copy.deepcopy(row[key])
            for key in ("id", "decision", "reason", "severity_override", "duplicate_of")
            if key in row
        }
        for row in novel
    )
    response_by_id = {row["id"]: row for row in responses}
    accepted = [
        {
            **row,
            "severity": (response_by_id[row["id"]].get("severity_override") or {}).get("severity")
            or row["severity"],
        }
        for row in [*primary, *new_findings]
        if response_by_id[row["id"]]["decision"] == "accept"
    ]
    accepted.sort(
        key=lambda row: {"critical": 0, "high": 1, "medium": 2, "low": 3}[row["severity"]]
    )
    blocking = [row["id"] for row in accepted if row["severity"] != "low"]
    ci_assessments = copy.deepcopy(old_decision.get("ci_job_assessments") or [])
    if pending["scope"]["pipelines_changed"]:
        ci_assessments = copy.deepcopy(
            result.get("ci_job_assessments") or context.ci_job_assessment_template(evidence)
        )
    ci_blocked = context.ci_blocks_ready(evidence, ci_assessments)
    reasons = copy.deepcopy(old_decision.get("owner_decision_reasons") or [])
    if pending["scope"]["pipelines_changed"] and not ci_blocked:
        reasons = [
            reason
            for reason in reasons
            if reason
            not in {
                "Exact-head CI jobs are unsuccessful, incomplete, or not yet classified as process gates.",
                "Current CI evidence needs addressed classification.",
            }
        ]
    if ci_blocked and not blocking and not reasons:
        reasons = ["Current CI evidence needs addressed classification."]
    finalize_path, finalize_digest = contract.write_artifact(
        root,
        "finalize_report",
        {
            "status": "ok",
            "changed": [],
            "complete": True,
            "evidence_digest": progress["evidence_digest"],
            "evidence_kind": "evidence_snapshot",
            "evidence_fingerprint_digest": contract.digest(contract.fingerprint(evidence)),
            "head_sha": evidence["head_sha"],
            "external_mutations": False,
        },
    )
    decision = {
        **copy.deepcopy(old_decision),
        "evidence_digest": progress["evidence_digest"],
        "context_digest": progress["context_digest"],
        "critic_receipt_digest": receipt_digest,
        "finalize_digest": finalize_digest,
        "mode": progress["mode"],
        "findings": primary,
        "critic_findings": new_findings,
        "accepted_findings": accepted,
        "critic_target_finding_ids": fresh_receipt["target_finding_ids"],
        "responses": responses,
        "ci_job_assessments": ci_assessments,
        "owner_decision_reasons": reasons,
        "blocking_findings": bool(blocking),
        "blocking_finding_ids": blocking,
        "verdict": "not_ready" if blocking else "blocked" if ci_blocked or reasons else "ready",
    }
    contract.validate_decision(
        decision,
        str(progress["evidence_digest"]),
        fresh_receipt,
        str(progress["mode"]),
        str(progress["context_digest"]),
        receipt_digest,
    )
    decision_path, decision_digest = contract.write_artifact(root, "review_decision", decision)
    old_content = copy.deepcopy(state["content"])
    fresh_semver = review_semver.rendered_template(evidence, review_context)
    fresh_semver.update(
        {
            key: copy.deepcopy(old_content["semver_assessment"][key])
            for key in render.SEMVER_PROSE_KEYS
            if key in old_content["semver_assessment"]
            and (
                key in {"policy", "sources"}
                or fresh_semver["mode"] == old_content["semver_assessment"]["mode"]
            )
        }
    )
    old_content["semver_assessment"] = fresh_semver
    old_content["recommended_issues"] = [
        revised_issues.get(str(row["id"]), row)
        for row in old_content.get("recommended_issues", [])
        if str(row["id"]) not in closed_issues
    ]
    for assessment in old_content.get("previous_finding_assessments", []):
        if str(assessment["id"]) in closed_issues:
            assessment.update(status="withdrawn", rationale=closed_issues[str(assessment["id"])])
    bindings = context.expected_thread_bindings(review_context)
    existing_threads = {str(row["id"]): row for row in old_content["thread_decisions"]}
    fresh_content = context.content_template(evidence, review_context, decision, progress["locale"])
    old_content["thread_decisions"] = [
        existing_threads.get(str(row["id"]), row) for row in fresh_content["thread_decisions"]
    ]
    existing_labels = {str(row["name"]): row for row in old_content["label_assessments"]}
    old_content["label_assessments"] = [
        existing_labels.get(str(row["name"]), row) for row in fresh_content["label_assessments"]
    ]
    for thread in old_content["thread_decisions"]:
        binding = bindings.get(str(thread["id"]))
        if binding:
            thread.update(
                {
                    key: copy.deepcopy(binding[key])
                    for key in render.STRUCTURAL_THREAD_KEYS
                    if key in binding
                }
            )
    # Locate the same semantic source excerpt again; its position proves only
    # where to publish. Truth is supplied by the separate delta check above.
    for correction in corrections:
        resolved_correction = render.resolve_prose_fixes(
            old_content, correction, review_context, evidence
        )
        old_content = render.apply_prose(old_content, resolved_correction)
    prose = copy.deepcopy(state.get("prose") or render.prose_projection(old_content))
    prose["semver_assessment"] = render.prose_projection(old_content)["semver_assessment"]
    if corrections:
        projection = render.prose_projection(old_content, review_context, evidence)
        for correction in corrections:
            for key in correction:
                prose[key] = copy.deepcopy(projection[key])
    if (
        pending["scope"]["metadata_fields"]
        and "label_catalog" in pending["scope"]["metadata_fields"]
    ):
        prose["label_assessments"] = render.prose_projection(old_content)["label_assessments"]
        contract.write_json(Path(state["prose_path"]), prose)
    added = []
    for row in novel:
        if row["decision"] != "accept":
            continue
        existing_intents = {str(intent["finding_id"]): intent for intent in state["intents"]}
        if row.get("publication"):
            existing_intents[str(row["id"])] = {
                "finding_id": row["id"],
                "publication": copy.deepcopy(row["publication"]),
                "dependencies": copy.deepcopy(row["dependencies"]),
            }
        state["intents"] = list(existing_intents.values())
        added.append(
            {
                "finding_id": row["id"],
                "body": "<BODY: address this new delta finding>",
                "publication": row.get("publication")
                or {
                    "kind": "<KIND: choose the publication intent>",
                    "fix_mode": "<FIX_MODE: suggestion or patch>",
                },
            }
        )
    if added:
        prose["finding_publications"].extend(added)
        contract.write_json(Path(state["prose_path"]), prose)
    ids = {str(row["id"]) for row in accepted}
    prose["finding_publications"] = [
        row for row in prose.get("finding_publications", []) if str(row["finding_id"]) in ids
    ]
    old_content["finding_publications"] = [
        row for row in old_content["finding_publications"] if str(row["finding_id"]) in ids
    ]
    old_content["findings"] = copy.deepcopy(accepted)
    try:
        resolved = render.resolve_prose_fixes(old_content, prose, review_context, evidence)
        content = render.apply_prose(old_content, resolved)
        content["findings"] = copy.deepcopy(accepted)
        content["rejected_candidates"] = render.rejected_from_decision(
            decision, state["intents"], review_context
        )
        content = render.reconcile_history(content, decision, review_context)
        applied = (
            bool(state.get("applied")) and not added and not render.placeholder_guidance(content)
        )
        clarification = None
    except contract.WorkflowError as error:
        content, applied, clarification = old_content, False, str(error)
    state.update(decision_digest=decision_digest, content=content, prose=prose, applied=applied)
    if (
        corrections
        or added
        or clarification
        or "label_catalog" in pending["scope"]["metadata_fields"]
    ):
        contract.write_json(Path(state["prose_path"]), prose)
    state["delta_checks"] = [*state.get("delta_checks", []), str(check_path)]
    state.pop("pending_delta", None)
    if clarification:
        state["clarification"] = clarification
    save(root, state)
    context.advance_progress(
        root,
        "content_missing",
        critic_receipt_path=str(receipt_path),
        critic_receipt_digest=receipt_digest,
        finalize_report_path=str(finalize_path),
        finalize_report_digest=finalize_digest,
        decision_path=str(decision_path),
        decision_digest=decision_digest,
    )
    return {
        "status": "needs_targeted_repair" if clarification else "ok",
        "prose_path": state["prose_path"],
        "clarification": clarification,
        "history_path": str(history_path),
        "delta_result_path": str(check_path),
        "external_mutations": False,
    }
