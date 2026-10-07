"""Decision-driven content rendering, the prose surface, and drift re-anchoring.

The live-review tail inverted: once the decision (arbitration receipt or
dispositions) is recorded, the runtime renders the complete content draft -
machine fields (anchors, bindings, revisions, stamps) derived by calling the
same functions the validators call, prose fields as structurally detectable
placeholders. The agent edits only prose and semantic choices through one
file and one command; evidence drift re-anchors the machine fields instead of
re-authoring the review.
"""

from __future__ import annotations

import copy
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from reviewmatic import context, publication_skeletons
from reviewmatic.portable.portable_gitlab import contract, review_semver

# Prose and semantic keys the agent may edit through the prose surface; every
# other content key is machine-rendered and rejected here.
PROSE_KEYS = (
    "locale",
    "chat_assessment",
    "summary",
    "architecture_assessment",
    "semver_impact",
    "semver_rationale",
    "semver_assessment",
    "mr_metadata_assessment",
    "label_assessments",
    "checks",
    "previous_finding_assessments",
    "recommended_issues",
    "rejected_candidate_assessments",
    "thread_decisions",
    "finding_publications",
)
STRUCTURAL_THREAD_KEYS = {
    "url",
    "state",
    "last_note_id",
    "last_note_body_sha256",
    "thread_sha256",
    "suggestions",
}
STRUCTURAL_PUBLICATION_KEYS = {
    "type",
    "path",
    "line",
    "old_line",
    "fix_mode",
    "suggestions",
    "patch_path",
    "patch_sha256",
    "revision",
}
STRUCTURAL_ASSESSMENT_KEYS = {
    "critic_required",
    "previous_status",
    "current_status",
    "action",
    "publication_action",
    "publication_body",
    "revision",
    "update_issue",
}
SEMVER_PROSE_KEYS = {"policy", "sources", "fallback_reason", "release_impact", "release_rationale"}


def _accepted_findings(draft: dict[str, Any]) -> list[dict[str, Any]]:
    findings = [
        *_records_flat(draft.get("findings")),
        *[
            finding
            for receipt in _records_flat(draft.get("critics"))
            for finding in _records_flat(receipt.get("findings"))
        ],
    ]
    dispositions = {str(item.get("id")): item for item in _records_flat(draft.get("dispositions"))}
    accepted = []
    for finding in findings:
        disposition = dispositions.get(str(finding.get("id")))
        if disposition is not None and disposition.get("decision") == "accept":
            override = disposition.get("severity_override") or {}
            accepted.append(
                {**finding, "severity": override.get("severity") or finding["severity"]}
            )
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(accepted, key=lambda finding: order[finding["severity"]])


def _records_flat(value: object) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", value) if isinstance(value, list) else []


def _publication_intents(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
    arbitration = draft.get("arbitration")
    if isinstance(arbitration, dict):
        rows = _records_flat(arbitration.get("dispositions"))
    else:
        rows = _records_flat(draft.get("dispositions"))
    intents: dict[str, dict[str, Any]] = {}
    for row in rows:
        publication = row.get("publication")
        if isinstance(publication, dict):
            intents[str(row.get("id"))] = publication
    return intents


def _first_changed_line(
    repo_root: Path, base: str, head: str, paths: list[str]
) -> tuple[str, int] | None:
    anchors: list[tuple[str, int]] = []
    for path in paths:
        _, visible = context.changed_diff_lines(repo_root, base, head, path)
        diff = str(contract.git_read(repo_root, "diff", "--unified=0", base, head, "--", path))
        for match in re.finditer(r"^@@ -[^ ]+ \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
            start, count = int(match[1]), int(match[2]) if match[2] is not None else 1
            anchors.extend((path, line) for line in range(start, start + count) if line in visible)
    return anchors[0] if len(anchors) == 1 else None


def targeted_suggestion(
    repo_root: Path,
    base: str,
    head: str,
    target: dict[str, Any],
    replacement: str,
    body: str,
) -> dict[str, Any]:
    """Locate a semantic source excerpt and derive the GitLab range, never guess."""
    if set(target) != {"path", "before"} or not all(
        isinstance(target[key], str) and target[key] for key in target
    ):
        raise contract.WorkflowError(
            "target needs path and before: the exact source excerpt, not line numbers"
        )
    path, before = str(target["path"]), str(target["before"])
    if path.startswith("/") or ".." in Path(path).parts:
        raise contract.WorkflowError("target.path must be a repository-relative file")
    source = str(contract.git_read(repo_root, "show", f"{head}:{path}")).splitlines()
    snippet = before.splitlines()
    matches = [
        index
        for index in range(len(source) - len(snippet) + 1)
        if source[index : index + len(snippet)] == snippet
    ]
    if len(matches) != 1:
        positions = ", ".join(str(index + 1) for index in matches) or "none"
        raise contract.WorkflowError(
            f"target.before has {len(matches)} matches in {path} (candidate starts: {positions}); "
            "clarify the exact source excerpt, including distinguishing context; existing prose is retained"
        )
    start, end = matches[0] + 1, matches[0] + len(snippet)
    _, visible = context.changed_diff_lines(repo_root, base, head, path)
    anchors = sorted(visible & set(range(start, end + 1)))
    if not anchors:
        raise contract.WorkflowError(
            f"target in {path}:{start}-{end} has no visible diff anchor; choose an affected source excerpt"
        )
    # Select a visible anchor that stays within GitLab's bounded range limits.
    anchor = next(
        (line for line in reversed(anchors) if line - start <= 100 and end - line <= 100), None
    )
    if anchor is None:
        raise contract.WorkflowError(
            "target exceeds the suggestion range limit; split the semantic fix into bounded parts"
        )
    payload = replacement[:-1] if replacement.endswith("\n") else replacement
    suggestion = f"```suggestion:-{anchor - start}+{end - anchor}\n{payload}\n```"
    return {
        "path": path,
        "line": anchor,
        "old_line": None,
        "body": f"{body.rstrip()}\n\n{suggestion}",
    }


def suggestion_target(
    row: dict[str, Any], review_context: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    """Expose source text, not machine positions, as the prose edit handle."""
    span = context.suggestion_blocks(str(row.get("body") or ""))
    before = int(span[0].group("before") or 0) if span else 0
    after = int(span[0].group("after") or 0) if span else 0
    line = row.get("line")
    if not isinstance(line, int) or not isinstance(row.get("path"), str):
        return {"path": publication_skeletons.PATH_HINT, "before": "<BEFORE: exact source excerpt>"}
    repo = Path(str(review_context["exact_git"]["repo_root"]))
    source = str(contract.git_read(repo, "show", f"{evidence['head_sha']}:{row['path']}"))
    return {
        "path": row["path"],
        "before": "\n".join(source.splitlines()[line - before - 1 : line + after]),
    }


def resolve_prose_fixes(
    content: dict[str, Any],
    incoming: dict[str, Any],
    review_context: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Translate semantic fix payloads to the input publication shape."""
    result = copy.deepcopy(incoming)
    semver = result.get("semver_assessment")
    if isinstance(semver, dict) and "basis" in semver:
        basis = semver.pop("basis")
        if basis is None:
            content["semver_assessment"] = review_semver.template(evidence, review_context)
        else:
            if not isinstance(basis, dict):
                raise contract.WorkflowError(
                    "semver_assessment.basis: return {name,source} from the collected catalog or null for explicit target-branch fallback"
                )
            content["semver_assessment"] = review_semver.rendered_template(
                evidence, review_context, basis
            )
    threads = {str(row["id"]): row for row in content.get("thread_decisions", [])}
    for row in result.get("thread_decisions", []):
        prepared_thread = threads.get(str(row.get("id")))
        if prepared_thread is None:
            continue
        parts = row.pop("parts", None)
        if "replacement" in row:
            if parts is not None:
                raise contract.WorkflowError(
                    "thread_decisions: choose target/replacement or parts, not both"
                )
            parts = [{"target": row.pop("target", None), "replacement": row.pop("replacement")}]
        if parts is None:
            continue
        if (
            row.get("fix_mode", prepared_thread.get("fix_mode")) != "suggestion"
            or not isinstance(parts, list)
            or not 1 <= len(parts) <= 50
        ):
            raise contract.WorkflowError(
                "thread_decisions.parts: use fix_mode=suggestion with 1..50 semantic target/replacement parts"
            )
        suggestions = []
        for part in parts:
            if (
                not isinstance(part, dict)
                or set(part) - {"target", "replacement", "body"}
                or not isinstance(part.get("replacement"), str)
            ):
                raise contract.WorkflowError(
                    "thread_decisions.parts: each part needs target {path,before}, replacement text, and optional body; positions are runtime-owned"
                )
            located = targeted_suggestion(
                Path(str(review_context["exact_git"]["repo_root"])),
                str(evidence["base_sha"]),
                str(evidence["head_sha"]),
                part.get("target") or {},
                part["replacement"],
                str(part.get("body") or row.get("proposed_response") or ""),
            )
            suggestions.append({key: located[key] for key in ("path", "line", "body")})
        prepared_thread["suggestions"] = suggestions
    current = {str(row["finding_id"]): row for row in content.get("finding_publications", [])}
    for row in result.get("finding_publications", []):
        prepared = current.get(str(row.get("finding_id")))
        if prepared is None:
            continue
        parts = row.pop("parts", None)
        if parts is not None:
            if (
                prepared.get("fix_mode") != "suggestion"
                or not isinstance(parts, list)
                or not parts
                or len(parts) > 50
            ):
                raise contract.WorkflowError("parts requires 1..50 semantic suggestion payloads")
            built = []
            for part in parts:
                if (
                    not isinstance(part, dict)
                    or set(part) - {"target", "replacement", "body"}
                    or not isinstance(part.get("replacement"), str)
                ):
                    raise contract.WorkflowError(
                        "each part needs target {path,before}, replacement text, and optional explanation body; positions are runtime-owned"
                    )
                located = targeted_suggestion(
                    Path(str(review_context["exact_git"]["repo_root"])),
                    str(evidence["base_sha"]),
                    str(evidence["head_sha"]),
                    part.get("target") or {},
                    part["replacement"],
                    str(part.get("body") or row.get("body") or ""),
                )
                built.append({key: located[key] for key in ("path", "line", "body")})
            prepared["suggestions"] = built
            if prepared.get("type") == "line":
                prepared["path"], prepared["line"], prepared["old_line"] = (
                    built[0]["path"],
                    built[0]["line"],
                    None,
                )
            else:
                prepared["path"], prepared["line"], prepared["old_line"] = None, None, None
            row["patch"] = None
            continue
        if prepared.get("fix_mode") == "suggestion" and "replacement" in row:
            replacement = row.pop("replacement")
            target = row.pop("target", None) or suggestion_target(
                prepared, review_context, evidence
            )
            if replacement != "" and publication_skeletons.is_placeholder(replacement):
                row["body"] = str(replacement)
                continue
            if not isinstance(replacement, str):
                raise contract.WorkflowError(
                    "replacement must be text (empty text deletes the source excerpt)"
                )
            located = targeted_suggestion(
                Path(str(review_context["exact_git"]["repo_root"])),
                str(evidence["base_sha"]),
                str(evidence["head_sha"]),
                target,
                replacement,
                str(row.get("body") or ""),
            )
            prepared.update({key: located[key] for key in ("path", "line", "old_line")})
            row["body"] = located["body"]
    return result


def copied_presentation(
    value: object,
    evidence: dict[str, Any],
    review_context: dict[str, Any],
    _tokens: set[str] | None = None,
) -> Any:
    """Scrub copied prose recursively; immutable original evidence is not edited."""
    if _tokens is None:
        _tokens = {
            sha[:length].casefold()
            for sha, _source in context.raw_ref_sources(evidence, review_context)
            for length in range(7, len(sha) + 1)
        }
    if isinstance(value, list):
        return [copied_presentation(item, evidence, review_context, _tokens) for item in value]
    if isinstance(value, dict):
        return {
            key: copy.deepcopy(item)
            if key
            in {
                "evidence_digest",
                "context_digest",
                "scope_digest",
                "thread_sha256",
                "last_note_body_sha256",
                "target_sha",
                "sha",
                "url",
                "patch",
                "patch_sha256",
                "patch_path",
                "head_sha",
                "base_sha",
                "start_sha",
                "from_head",
                "to_head",
                "command",
                "path",
                "repo_root",
                "source_repo_root",
            }
            else copied_presentation(item, evidence, review_context, _tokens)
            for key, item in value.items()
        }
    if not isinstance(value, str):
        return value
    # Preserve executable fix code and immutable revision links. Token lookup
    # avoids re-scanning every release/tag SHA for every copied text field.
    pieces = re.split(
        r"(^`{3,}[^\n]*\n.*?^`{3,}[ \t]*$|https?://[^\s)]+)", value, flags=re.MULTILINE | re.DOTALL
    )
    tokens = _tokens
    for index in range(0, len(pieces), 2):
        pieces[index] = re.sub(
            r"(?<![0-9a-f])[0-9a-f]{7,64}(?![0-9a-f])",
            lambda match: "reviewed revision" if match[0].casefold() in tokens else match[0],
            pieces[index],
            flags=re.IGNORECASE,
        )
    for index in range(1, len(pieces), 2):
        if (
            pieces[index].startswith(("http://", "https://"))
            and not pieces[index - 1].endswith("](")
            and any(
                match[0].casefold() in tokens
                for match in re.finditer(r"[0-9a-f]{7,64}", pieces[index], flags=re.IGNORECASE)
            )
        ):
            pieces[index] = f"[reviewed revision]({pieces[index]})"
    return "".join(pieces)


def reconcile_history(
    content: dict[str, Any], decision: dict[str, Any], review_context: dict[str, Any]
) -> dict[str, Any]:
    """Derive re-publication structure from the immutable finalized baseline."""
    result = copy.deepcopy(content)
    incremental = review_context.get("incremental") or {}
    old = {str(row["id"]): row for row in incremental.get("previous_finding_ledger", [])}
    authored = {str(row["id"]): row for row in result.get("previous_finding_assessments", [])}
    findings = {str(row["id"]): row for row in result.get("findings", [])}
    publications = {str(row["finding_id"]): row for row in result.get("finding_publications", [])}
    issues = {str(row["id"]): row for row in result.get("recommended_issues", [])}
    targets = set(decision.get("critic_target_finding_ids") or [])
    reasons = {
        str(row["id"]): str(row.get("reason") or "") for row in decision.get("responses", [])
    }
    rows = []
    for identifier, prior in old.items():
        kind = str(prior["kind"])
        row = authored.get(identifier) or {}
        current = findings.get(identifier) if kind == "finding" else issues.get(identifier)
        previous = copy.deepcopy(prior["record"][kind])
        previous.pop("revision", None)
        changed = current is not None and current != previous
        if kind == "finding" and current is not None:
            previous_publication = {
                key: value
                for key, value in prior["record"]["publication"].items()
                if key not in {"revision", "patch_path", "patch_sha256"}
            }
            changed = changed or publications.get(identifier) != previous_publication
        if current is not None:
            status = "changed" if changed or prior["status"] in {"fixed", "withdrawn"} else "active"
        else:
            status = str(row.get("status") or "unverified")
            if status not in {"fixed", "withdrawn"}:
                status = "unverified"
        if kind == "issue":
            # Follow-ups are proposals, not a second issue-publication workflow.
            publication_action, publication_body = "no_publication", None
        elif status == "changed":
            publication_action = "reply"
            publication_body = str(
                (publications.get(identifier) or {}).get("body")
                or row.get("publication_body")
                or ""
            )
        else:
            publication_action = "no_publication"
            publication_body = None
        rows.append(
            {
                "id": identifier,
                "kind": kind,
                "status": status,
                "previous_status": str(prior["status"]),
                "current_status": status,
                "rationale": str(
                    row.get("rationale")
                    or reasons.get(identifier)
                    or "<RATIONALE: verify this prior conclusion>"
                ),
                "action": "Update the confirmed fix."
                if status == "changed"
                else "Retain the confirmed conclusion."
                if status == "active"
                else "Record the verified closure."
                if status in {"fixed", "withdrawn"}
                else "Verify the prior conclusion.",
                "publication_action": publication_action,
                "publication_body": publication_body,
                "critic_required": status in {"changed", "unverified"} or identifier in targets,
            }
        )
    result["previous_finding_assessments"] = rows
    # Use the same revision function as plan materialization, never an increment
    # of a previously rendered draft (which would count drift twice).
    context.finding_revisions(incremental, rows, set(findings))
    return result


def render_content(
    draft: dict[str, Any],
    review_context: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Render the complete content from the recorded decision.

    Machine fields are derived by the same functions the validators call;
    prose fields carry structurally detectable placeholders.
    """
    decision = _decision_for_content(draft)
    exact = cast("dict[str, Any]", review_context["exact_git"])
    repo_root = Path(str(exact["repo_root"]))
    base, head = str(evidence["base_sha"]), str(evidence["head_sha"])
    locale = "ru" if str(draft.get("content", {}).get("locale", "en")) == "ru" else "en"
    content = context.content_template(evidence, review_context, decision, locale)
    content["semver_assessment"] = review_semver.rendered_template(evidence, review_context)
    accepted = _accepted_findings(draft)
    intents = _publication_intents(draft)
    role = str(review_context.get("role", "reviewer"))
    rows: list[dict[str, Any]] = []
    for finding in accepted:
        finding_id = str(finding.get("id"))
        intent = intents.get(finding_id)
        if intent is None or intent.get("kind") == "none":
            raise contract.WorkflowError(
                f"accepted finding {finding_id} requires a publication intent with a concrete "
                "fix; none cannot hide an accepted finding - reject or merge it in arbitration"
            )
        if intent.get("kind") == "existing_thread":
            block = publication_skeletons._variant_block(finding_id, "existing_thread")
            thread_ids = [
                str(thread_id)
                for row in _records_flat(draft.get("dispositions"))
                if row.get("id") == finding_id
                for thread_id in (row.get("dependencies") or {}).get("thread_ids", [])
            ]
            bindings = context.expected_thread_bindings(review_context)
            if len(thread_ids) != 1 or thread_ids[0] not in bindings:
                raise contract.WorkflowError(
                    f"existing_thread intent for {finding_id} needs one prepared thread in "
                    "dependencies.thread_ids; use decision repair rather than guessing a thread"
                )
            block["thread_id"] = thread_ids[0]
            rows.append(block)
            continue
        if intent.get("kind") == "local_fix" and role == "author":
            if intent.get("fix_mode") != "patch":
                raise contract.WorkflowError("author local_fix intent requires a unified patch")
            rows.append(publication_skeletons._variant_block(finding_id, "local_fix+patch"))
            continue
        if intent.get("kind") == "local_fix":
            raise contract.WorkflowError(
                "reviewer intent cannot silently become an author's local_fix"
            )
        if intent.get("kind") == "line":
            block = publication_skeletons._variant_block(
                finding_id,
                "line+suggestion" if intent.get("fix_mode") == "suggestion" else "line+patch",
            )
            target = intent.get("target")
            if isinstance(target, dict):
                located = targeted_suggestion(
                    repo_root,
                    base,
                    head,
                    target,
                    "<REPLACEMENT: corrected source>",
                    publication_skeletons.BODY_HINT,
                )
                block.update({key: located[key] for key in ("path", "line", "old_line")})
                if block["fix_mode"] == "suggestion":
                    block["body"] = located["body"]
                rows.append(block)
                continue
            dependencies = _dependencies_of(draft, finding_id)
            anchor = _first_changed_line(repo_root, base, head, dependencies)
            if anchor is not None:
                block["path"], block["line"] = anchor[0], anchor[1]
            elif len(dependencies) == 1:
                # The prose file asks for an exact excerpt. No arbitrary line
                # is selected when several edited lines are possible.
                block["path"] = dependencies[0]
            rows.append(block)
            continue
        if intent.get("fix_mode") == "suggestion":
            block = publication_skeletons._variant_block(finding_id, "general+patch")
            block.update(
                fix_mode="suggestion",
                patch=None,
                suggestions=[],
                split_rationale=publication_skeletons.SPLIT_RATIONALE_HINT,
            )
            block.pop("patch_reason", None)
            rows.append(block)
            continue
        rows.append(
            publication_skeletons._variant_block(
                finding_id,
                "general+patch",
            )
        )
    content["finding_publications"] = rows
    content["findings"] = accepted
    # Scrub at render time on machine-copied texts: semver sources and the
    # previous-finding rows are copied by the runtime, so a raw SHA inside
    # them is refused here, at the moment of copying.
    # Findings are immutable decision data. Scrub their user-facing projection
    # in the Markdown/chat builders, not the evidence preserved in JSON.
    projected = cast("dict[str, Any]", copied_presentation(content, evidence, review_context))
    projected["findings"] = accepted
    projected["rejected_candidates"] = content["rejected_candidates"]
    return projected


def _dependencies_of(draft: dict[str, Any], finding_id: str) -> list[str]:
    arbitration = draft.get("arbitration")
    rows = (
        _records_flat(arbitration.get("dispositions"))
        if isinstance(arbitration, dict)
        else _records_flat(draft.get("dispositions"))
    )
    for row in rows:
        if str(row.get("id")) == finding_id:
            dependencies = row.get("dependencies")
            if isinstance(dependencies, dict):
                return [str(item) for item in cast("list[object]", dependencies.get("paths") or [])]
    return []


def _decision_for_content(draft: dict[str, Any]) -> dict[str, Any]:
    accepted = _accepted_findings(draft)
    return {
        "accepted_findings": accepted,
        "findings": _records_flat(draft.get("findings")),
        "critic_findings": [
            finding
            for receipt in _records_flat(draft.get("critics"))
            for finding in _records_flat(receipt.get("findings"))
        ],
        "responses": [
            {"id": row["id"], "decision": row["decision"], "reason": row["reason"]}
            for row in _records_flat(draft.get("dispositions"))
        ],
    }


def rejected_from_decision(
    decision: dict[str, Any], intents: list[dict[str, Any]], review_context: dict[str, Any]
) -> list[dict[str, Any]]:
    responses = {str(row["id"]): row for row in decision.get("responses", [])}
    dependencies = {str(row["finding_id"]): row.get("dependencies") for row in intents}
    rejected = []
    for source, findings in (
        ("primary", decision.get("findings") or []),
        ("critic", decision.get("critic_findings") or []),
    ):
        for finding in findings:
            response = responses.get(str(finding["id"]))
            if response and response["decision"] == "reject":
                rejected.append(
                    {
                        "id": finding["id"],
                        "source": source,
                        "finding": copy.deepcopy(finding),
                        "reason": response["reason"],
                        **(
                            dependencies.get(str(finding["id"]))
                            or {
                                "paths": review_context["exact_git"].get("changed_paths", []),
                                "thread_ids": [],
                                "metadata_fields": [],
                                "ci": False,
                            }
                        ),
                    }
                )
    return rejected


def prose_file(root: Path, context_digest: str) -> Path:
    return root / "review-drafts" / f"content-prose-{context_digest[:16]}.json"


def prose_projection(
    content: dict[str, Any],
    review_context: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The prose surface: agent-editable fields only, machine keys stripped."""
    projection: dict[str, Any] = {}
    for key in PROSE_KEYS:
        if key not in content:
            continue
        value = copy.deepcopy(content[key])
        if key == "thread_decisions" and isinstance(value, list):
            projection[key] = [
                {field: item[field] for field in item if field not in STRUCTURAL_THREAD_KEYS}
                for item in value
                if isinstance(item, dict)
            ]
            if review_context is not None and evidence is not None:
                for original, row in zip(value, projection[key], strict=True):
                    if original.get("fix_mode") == "suggestion" and original.get("suggestions"):
                        row["parts"] = [
                            {
                                "target": suggestion_target(part, review_context, evidence),
                                "replacement": context.suggestion_blocks(part["body"])[0]
                                .group("replacement")
                                .removesuffix("\n"),
                                "body": context.SUGGESTION_RE.sub("", part["body"]).strip(),
                            }
                            for part in original["suggestions"]
                        ]
        elif key == "finding_publications" and isinstance(value, list):
            projection[key] = [
                {field: item[field] for field in item if field not in STRUCTURAL_PUBLICATION_KEYS}
                for item in value
                if isinstance(item, dict)
            ]
            if review_context is not None and evidence is not None:
                for original, row in zip(value, projection[key], strict=True):
                    if original.get("fix_mode") == "suggestion":
                        if "suggestions" in original:
                            row["parts"] = [
                                {
                                    "target": suggestion_target(part, review_context, evidence),
                                    "replacement": context.suggestion_blocks(part["body"])[0]
                                    .group("replacement")
                                    .removesuffix("\n"),
                                    "body": context.SUGGESTION_RE.sub("", part["body"]).strip(),
                                }
                                for part in original["suggestions"]
                            ]
                            row.pop("patch", None)
                            continue
                        row["target"] = suggestion_target(original, review_context, evidence)
                        matches = context.suggestion_blocks(str(original.get("body") or ""))
                        row["replacement"] = (
                            matches[0].group("replacement").removesuffix("\n")
                            if matches
                            else "<REPLACEMENT: corrected source>"
                        )
                        row["body"] = context.SUGGESTION_RE.sub(
                            "", str(original.get("body") or "")
                        ).strip()
                        row.pop("patch", None)
        elif key == "previous_finding_assessments" and isinstance(value, list):
            projection[key] = [
                {field: item[field] for field in item if field not in STRUCTURAL_ASSESSMENT_KEYS}
                for item in value
                if isinstance(item, dict)
            ]
        elif key == "semver_assessment" and isinstance(value, dict):
            projection[key] = {field: value[field] for field in SEMVER_PROSE_KEYS if field in value}
            baseline = value.get("baseline")
            projection[key]["basis"] = (
                {field: baseline[field] for field in ("name", "source")}
                if isinstance(baseline, dict)
                else None
            )
        elif key == "label_assessments" and isinstance(value, list):
            projection[key] = [
                {field: row[field] for field in ("name", "status", "rationale")} for row in value
            ]
        else:
            projection[key] = value
    return projection


def apply_prose(content: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Apply the prose surface onto rendered content; structural keys refuse."""
    structural_rejections: list[str] = []
    merged = copy.deepcopy(content)
    for key, value in incoming.items():
        if key not in PROSE_KEYS:
            raise contract.WorkflowError(
                f"the prose surface carries only prose and semantic fields; {key} is "
                "machine-rendered - edit it only through a recorded repair kind"
            )
        if key == "semver_assessment":
            if not isinstance(value, dict) or set(value) - SEMVER_PROSE_KEYS:
                raise contract.WorkflowError(
                    "semver_assessment machine-rendered bindings cannot be set in record-prose; "
                    "edit policy, sources, fallback_reason, release_impact, or release_rationale"
                )
            merged[key] = {**merged[key], **copy.deepcopy(value)}
            continue
        if key in {"thread_decisions", "finding_publications", "previous_finding_assessments"} and (
            not isinstance(value, list) or any(not isinstance(row, dict) for row in value)
        ):
            raise contract.WorkflowError(
                f"{key} requires an array of prose objects; draft unchanged"
            )
        if key in {"thread_decisions", "finding_publications", "previous_finding_assessments"}:
            identity_key = "finding_id" if key == "finding_publications" else "id"
            identifiers = [row.get(identity_key) for row in value]
            if any(not isinstance(identifier, str) for identifier in identifiers) or len(
                set(identifiers)
            ) != len(identifiers):
                raise contract.WorkflowError(
                    f"{key}[*].{identity_key}: return each prepared row identifier once, unchanged; do not invent identities"
                )
        if key == "thread_decisions" and isinstance(value, list):
            rows: list[dict[str, Any]] = []
            current = {
                str(item.get("id")): item
                for item in cast("list[dict[str, Any]]", merged.get(key) or [])
                if isinstance(item, dict)
            }
            for row in value:
                if not isinstance(row, dict):
                    continue
                allowed = (
                    set(current.get(str(row.get("id"))) or {})
                    | {"patch_reason", "split_rationale", "severity", "routing_response"}
                ) - STRUCTURAL_THREAD_KEYS
                leak = sorted(set(row) - allowed)
                if leak:
                    structural_rejections.append(f"thread_decisions[{row.get('id')}]: {leak}")
                    continue
                base = current.get(str(row.get("id")))
                if base is None:
                    structural_rejections.append(
                        f"thread_decisions: unknown thread id {row.get('id')}"
                    )
                    continue
                rows.append({**base, **row})
            current.update({str(row["id"]): row for row in rows})
            merged[key] = list(current.values())
            continue
        if key == "finding_publications" and isinstance(value, list):
            rows = []
            current = {
                str(item.get("finding_id")): item
                for item in cast("list[dict[str, Any]]", merged.get(key) or [])
                if isinstance(item, dict)
            }
            for row in value:
                if not isinstance(row, dict):
                    continue
                allowed = (
                    set(current.get(str(row.get("finding_id"))) or {})
                    | {"body", "patch", "patch_reason", "split_rationale"}
                ) - STRUCTURAL_PUBLICATION_KEYS
                leak = sorted(set(row) - allowed)
                if leak:
                    structural_rejections.append(
                        f"finding_publications[{row.get('finding_id')}]: {leak}"
                    )
                    continue
                base = current.get(str(row.get("finding_id")))
                if base is None:
                    structural_rejections.append(
                        f"finding_publications: unknown finding id {row.get('finding_id')}"
                    )
                    continue
                rows.append({**base, **row})
            current.update({str(row["finding_id"]): row for row in rows})
            merged[key] = list(current.values())
            continue
        if key == "previous_finding_assessments" and isinstance(value, list):
            rows = []
            current = {
                f"{item.get('id')}\x00{item.get('kind') or ''}": item
                for item in cast("list[dict[str, Any]]", merged.get(key) or [])
                if isinstance(item, dict)
            }
            for row in value:
                if not isinstance(row, dict):
                    continue
                leak = sorted(STRUCTURAL_ASSESSMENT_KEYS & set(row))
                if leak:
                    structural_rejections.append(
                        f"previous_finding_assessments[{row.get('id')}]: {leak}"
                    )
                    continue
                matches = [
                    item for key2, item in current.items() if key2.split("\x00")[0] == row.get("id")
                ]
                if not matches:
                    structural_rejections.append(
                        f"previous_finding_assessments: unknown id {row.get('id')}"
                    )
                    continue
                base = matches[0]
                base_dict: dict[str, Any] = matches[0]
                identity_key = f"{row.get('id')}\x00{base_dict.get('kind') or ''}"
                rows.append({**base_dict, **row})
                del current[identity_key]
            merged[key] = rows
            continue
        if key == "label_assessments":
            current = {str(row["name"]): row for row in merged[key]}
            if not isinstance(value, list) or any(
                not isinstance(row, dict)
                or set(row) != {"name", "status", "rationale"}
                or not isinstance(row.get("name"), str)
                or row.get("name") not in current
                for row in value
            ):
                raise contract.WorkflowError(
                    "label_assessments: use prepared {name,status,rationale} rows, without output fields or unknown names; retain complete catalog coverage"
                )
            names = [row["name"] for row in value]
            if len(set(names)) != len(names):
                raise contract.WorkflowError(
                    "label_assessments[*].name: return each prepared label once"
                )
            current.update({str(row["name"]): copy.deepcopy(row) for row in value})
            merged[key] = list(current.values())
            continue
        if key == "mr_metadata_assessment" and isinstance(value, dict):
            merged[key].update(copy.deepcopy(value))
            continue
        merged[key] = value
    if structural_rejections:
        raise contract.WorkflowError(
            "structural keys are machine-rendered and were rejected: "
            + "; ".join(structural_rejections)
        )
    return merged


def placeholder_guidance(content: dict[str, Any]) -> list[dict[str, str]]:
    """Fill guidance for every unfilled prose placeholder, rule errors skipped."""
    guidance: list[dict[str, str]] = []
    for index, row in enumerate(_records_flat(content.get("finding_publications"))):
        fields = publication_skeletons.placeholder_fields(row)
        if fields:
            guidance.append(
                {
                    "path": f"$.content.finding_publications[{index}]",
                    "message": (
                        "unfilled template variant: fill the judgment fields "
                        f"{', '.join(fields)} or delete the unused variant rows"
                    ),
                }
            )
    for key in ("summary", "architecture_assessment", "semver_rationale"):
        value = content.get(key)
        if isinstance(value, str) and (
            not value.strip() or publication_skeletons.is_placeholder(value)
        ):
            guidance.append(
                {
                    "path": f"$.content.{key}",
                    "message": "fill the prose through the content prose file and record-prose",
                }
            )
    semantic_fields: list[tuple[str, object]] = []
    semver = content.get("semver_assessment") or {}
    for field in ("policy", "fallback_reason", "release_impact", "release_rationale"):
        if semver.get(field) is not None:
            semantic_fields.append((f"$.content.semver_assessment.{field}", semver[field]))
    for key, field in (("label_assessments", "rationale"), ("thread_decisions", "rationale")):
        semantic_fields.extend(
            (f"$.content.{key}[{index}].{field}", row.get(field))
            for index, row in enumerate(_records_flat(content.get(key)))
        )
    for field, row in (content.get("mr_metadata_assessment") or {}).items():
        semantic_fields.append(
            (f"$.content.mr_metadata_assessment.{field}.rationale", row.get("rationale"))
        )
    for path, value in semantic_fields:
        if value is None or (
            isinstance(value, str)
            and (not value.strip() or publication_skeletons.is_placeholder(value))
        ):
            guidance.append(
                {
                    "path": path,
                    "message": "fill this missing substantive assessment through record-prose; retain other authored fields",
                }
            )
    return guidance


def re_anchor_line(
    repo_root: Path, old_head: str, new_head: str, publications: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deterministic old-to-new line mapping for positioned publications."""
    remapped = copy.deepcopy(publications)
    for row in remapped:
        if row.get("type") != "line":
            continue
        path, line = str(row.get("path") or ""), row.get("line")
        if not path or not isinstance(line, int):
            continue
        diff = str(
            contract.git_read(repo_root, "diff", "--unified=0", old_head, new_head, "--", path)
        )
        offset = 0
        for match in re.finditer(
            r"^@@ -(?P<old>[0-9]+)(?:,(?P<old_count>[0-9]+))? \+(?P<new>[0-9]+)(?:,(?P<new_count>[0-9]+))? @@",
            diff,
            re.MULTILINE,
        ):
            old_start = int(match.group("old"))
            old_count = int(match.group("old_count")) if match.group("old_count") else 1
            new_count = int(match.group("new_count")) if match.group("new_count") else 1
            # An insertion (-N,0) occurs after N, not before N.
            if old_count == 0:
                if line > old_start:
                    offset += new_count
                continue
            if old_start <= line < old_start + old_count:
                raise contract.WorkflowError(
                    "the anchor is inside a changed hunk and has no unique image on the new "
                    f"head ({path}:{line}); use decision repair, never a guess"
                )
            if line >= old_start + old_count:
                offset += new_count - old_count
        row["line"] = line + offset
    return remapped


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
