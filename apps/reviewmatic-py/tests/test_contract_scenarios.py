"""Contract scenarios ported from ``contract.test.mjs``.

``test_contract_validators.py`` already carries the validator, label, preview,
critic, and decision scenarios; they are re-checked here only where the TS
test asserts more (duplicate findings in a decision). The collection and
transport scenarios replace the Node-script ``glab`` with Python scripts from
``helpers.contract_support``. Differences from the TypeScript runtime:

* ``glab_text`` and ``parse_glab_trace`` return ``(text, complete)`` tuples and
  ``parse_semver`` returns tuples, where TypeScript returns objects and arrays.
* Artifact timestamps follow the Python validator (decision 33): the strict
  extended ISO-8601 grammar, see ``probe-v2-divergence.mjs``.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any

import pytest
from helpers.contract_support import (
    CREATED_AT,
    DIGEST,
    component,
    context_payload,
    critic_payload,
    decision_payload,
    detailed_finding,
    evidence_payload,
    install_glab,
    review_plan_payload,
    use_state_home,
)

from reviewmatic.portable.portable_gitlab import contract

TARGET = {"hostname": "gitlab.example", "project_id": 42, "kind": "merge_requests", "iid": 7}


def workflow_error(match: str) -> Any:
    return pytest.raises(contract.WorkflowError, match=match)


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_digests_match_the_reference_serialization() -> None:
    values: list[Any] = [
        {"b": 1, "a": "plain"},
        {"ключ": "значение", "nested": {"z": "日本語", "y": ["α", "ω"]}},
        ["array", ["nested", []], 0, -17, True, False, None],
        {"control": "line\nbreak\ttab\u0001bell", "empty": ""},
        "",
        {"deep": {"deeper": {"deepest": {"leaf": "🚀"}}}},
        {"unicode_key_é": "é"},
    ]
    for value in values:
        reference = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
        assert contract.digest(value) == hashlib.sha256(reference.encode()).hexdigest()
        assert contract.canonical(value) == reference.encode()
        assert contract.canonical(value).decode().endswith("\n")


def test_redact_covers_every_secret_pattern_family() -> None:
    cases = {
        "api token = secret1,": "api token=[REDACTED],",
        '{"password": "hunter2"}': '{"password": "[REDACTED]"}',
        "Authorization: Bearer abc123\nnext": "Authorization: [REDACTED]\nnext",
        "AWS_SECRET_ACCESS_KEY=deadbeef done": "AWS_SECRET_ACCESS_KEY=[REDACTED] done",
        "see https://alice:hunter@gitlab.example/x now": "see https://[REDACTED]@gitlab.example/x now",
        "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----": "[REDACTED PRIVATE KEY]",
        "plain text without secrets": "plain text without secrets",
    }
    for value, expected in cases.items():
        assert contract.redact(value) == expected


def test_emit_prints_sorted_json_with_a_trailing_newline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract.emit({"b": 1, "a": "x"})
    assert capsys.readouterr().out == '{"a": "x", "b": 1}\n'


def test_capabilities_emits_the_code_review_profile_shape(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = contract.capabilities("code-review")
    captured = capsys.readouterr().out
    assert code == 0
    assert captured.startswith('{"destructive_flags": [], "dry_run": true, ')
    value = json.loads(captured)
    assert sorted(value) == [
        "destructive_flags",
        "dry_run",
        "external_mutations",
        "external_tools",
        "mutation",
        "payload_version",
        "profile",
        "schema_version",
        "state_protocol",
    ]
    assert value["profile"] == "code-review"
    assert value["schema_version"] == 1
    assert value["payload_version"] == "2.0.0"
    assert value["mutation"] == "local-write"
    assert value["dry_run"] is True
    assert value["external_mutations"] is False
    assert value["state_protocol"] == "private-content-addressed-artifacts"
    assert value["destructive_flags"] == []
    assert isinstance(value["external_tools"]["glab"], bool)
    assert isinstance(value["external_tools"]["git"], bool)


def test_parse_target_accepts_exact_issue_and_merge_request_urls() -> None:
    target = contract.parse_target(
        "https://gitlab.example/group/proj/-/merge_requests/7/", {"merge_requests"}
    )
    assert target == {
        "url": "https://gitlab.example/group/proj/-/merge_requests/7/",
        "hostname": "gitlab.example",
        "project_path": "group/proj",
        "kind": "merge_requests",
        "iid": 7,
    }
    issue = contract.parse_target(
        "https://GitLab.example/group/proj/-/issues/12", {"issues", "merge_requests"}
    )
    assert issue["kind"] == "issues"
    assert issue["hostname"] == "gitlab.example"
    assert issue["iid"] == 12


def test_parse_target_rejects_unsafe_or_mismatched_urls() -> None:
    expected = {"merge_requests"}
    for url in (
        "https://gitlab.example/g/p/-/issues/1",
        "https://gitlab.example/g/p/-/merge_requests/1?x=1",
        "https://gitlab.example/g/p/-/merge_requests/1#frag",
        "http://gitlab.example/g/p/-/merge_requests/1",
        "https://user:pw@gitlab.example/g/p/-/merge_requests/1",
        "https://gitlab.example/g/p/-/merge_requests/0",
    ):
        with workflow_error("exact HTTPS GitLab"):
            contract.parse_target(url, expected)
    for url in (
        "https://gitlab.example/g/../p/-/merge_requests/1",
        "https://gitlab.example/g/./p/-/merge_requests/1",
    ):
        with workflow_error("project path is unsafe"):
            contract.parse_target(url, expected)


def test_parse_project_accepts_and_rejects_exact_project_urls() -> None:
    assert contract.parse_project("https://gitlab.example/group/proj/") == {
        "url": "https://gitlab.example/group/proj",
        "hostname": "gitlab.example",
        "project_path": "group/proj",
        "kind": "new_issue",
        "iid": 0,
    }
    for url in (
        "https://gitlab.example/-/proj",
        "https://gitlab.example/only",
        "https://gitlab.example/group/../proj",
        "http://gitlab.example/group/proj",
        "https://user@gitlab.example/group/proj",
    ):
        with workflow_error("exact HTTPS GitLab project URL"):
            contract.parse_project(url)


def test_state_directory_derives_the_canonical_content_addressed_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_state_home(monkeypatch, tmp_path)
    home = tmp_path / "state"
    identity = "gitlab.example:42:merge_requests:7"
    expected = home / "agent-skills" / "gitlab" / hashlib.sha256(identity.encode()).hexdigest()[:32]
    assert contract.state_directory("code-review", TARGET) == expected
    assert mode_of(expected) == 0o700
    by_path = contract.state_directory(
        "code-review",
        {
            "hostname": "gitlab.example",
            "project_path": "group/proj",
            "kind": "merge_requests",
            "iid": 7,
        },
    )
    path_identity = "gitlab.example:group/proj:merge_requests:7"
    assert (
        by_path
        == home
        / "agent-skills"
        / "gitlab"
        / hashlib.sha256(path_identity.encode()).hexdigest()[:32]
    )
    with workflow_error("workflow profile is unsafe"):
        contract.state_directory("unknown-profile", TARGET)


def test_artifact_root_enforces_the_canonical_collection_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_state_home(monkeypatch, tmp_path)
    home = tmp_path / "state"
    digest32 = "b" * 32
    canonical_root = home / "agent-skills" / "gitlab" / digest32
    assert contract.artifact_root(canonical_root) == canonical_root
    legacy_root = home / "agent-skills" / "task-triage" / ("c" * 20)
    assert contract.artifact_root(legacy_root) == legacy_root
    with workflow_error("outside canonical GitLab collection state"):
        contract.artifact_root(home / "agent-skills")
    with workflow_error("artifact root is unsafe"):
        contract.artifact_root(home / "agent-skills" / "gitlab" / digest32 / "nested")
    with workflow_error("outside canonical GitLab collection state"):
        contract.artifact_root(home / "elsewhere" / digest32)
    with workflow_error("outside canonical GitLab collection state"):
        contract.artifact_root(home / "agent-skills" / "task_triage" / ("c" * 20))
    assert (tmp_path / "state" / "agent-skills" / "gitlab").exists()


def test_write_artifact_roundtrips_every_code_review_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_state_home(monkeypatch, tmp_path)
    root = contract.state_directory("code-review", TARGET)
    kinds: dict[str, dict[str, Any]] = {
        "evidence_snapshot": evidence_payload(),
        "review_context": context_payload(),
        "critic_receipt": critic_payload(),
        "review_decision": decision_payload(),
        "review_plan": review_plan_payload(),
        "finalize_report": {
            "status": "ok",
            "changed": [],
            "complete": True,
            "head_sha": "c",
            "evidence_digest": DIGEST,
            "evidence_kind": "evidence_snapshot",
            "evidence_fingerprint_digest": DIGEST,
            "external_mutations": False,
        },
    }
    for kind, payload in kinds.items():
        path, digest_value = contract.write_artifact(root, kind, payload)
        assert len(digest_value) == 64
        assert path == root / "artifacts" / kind / f"{digest_value}.json"
        assert mode_of(path) == 0o600
        assert mode_of(path.parent) == 0o700
        document, recovered = contract.artifact_payload(path, kind)
        assert document["schema"] == f"portable-gitlab/{kind}/v2"
        assert recovered == payload


def test_artifact_payload_rejects_tampered_envelopes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_state_home(monkeypatch, tmp_path)
    root = contract.state_directory(
        "code-review",
        {"hostname": "gitlab.example", "project_id": 1, "kind": "merge_requests", "iid": 1},
    )
    path, _ = contract.write_artifact(root, "evidence_snapshot", evidence_payload())
    original = path.read_text(encoding="utf-8")

    kind_tampered = json.loads(original)
    kind_tampered["kind"] = "review_plan"
    path.write_text(json.dumps(kind_tampered))
    with workflow_error("artifact schema is invalid"):
        contract.artifact_payload(path, "evidence_snapshot")

    timestamp_tampered = json.loads(original)
    timestamp_tampered["created_at"] = "not-a-date"
    path.write_text(json.dumps(timestamp_tampered))
    with workflow_error("does not satisfy the canonical schema"):
        contract.artifact_payload(path, "evidence_snapshot")

    payload_tampered = json.loads(original)
    del payload_tampered["payload"]["profile"]
    path.write_text(json.dumps(payload_tampered))
    with workflow_error("does not satisfy the canonical schema"):
        contract.artifact_payload(path, "evidence_snapshot")

    path.write_text(original)
    _, recovered = contract.artifact_payload(path, "evidence_snapshot")
    assert recovered["profile"] == "code-review"

    v1 = json.loads(original)
    v1["schema_version"] = 1
    path.write_text(json.dumps(v1))
    v1_document, v1_payload = contract.artifact_payload(path, "evidence_snapshot")
    assert v1_document["schema_version"] == 1
    assert v1_payload is v1_document


def test_write_companion_is_immutable_and_conflict_checked(tmp_path: Path) -> None:
    path = tmp_path / "plan.md"
    resolved, digest_value = contract.write_companion(path, "body\n")
    assert resolved == path.resolve()
    assert digest_value == hashlib.sha256(b"body\n").hexdigest()
    _, again_digest = contract.write_companion(path, "body\n")
    assert again_digest == digest_value
    with workflow_error("immutable Markdown companion conflict"):
        contract.write_companion(path, "different\n")


def test_label_semantics_resolve_aliases_through_names_and_descriptions() -> None:
    assert contract.label_semantics({"name": "type::bug"}) == ("change_type", "bug")
    assert contract.label_semantics({"name": "priority::p1"}) == ("urgency", "urgent")
    assert contract.label_semantics({"name": "semver/patch"}) == ("compatibility", "patch")
    assert contract.label_semantics({"name": "state=in_progress"}) == (
        "workflow_state",
        "in_progress",
    )
    assert contract.label_semantics(
        {"name": "x", "description": "Semantic-Role: kind; Semantic-Value: defect"}
    ) == ("change_type", "bug")
    assert contract.label_semantics({"name": "unknown::bug"}) is None
    assert contract.label_semantics({"name": "one-part"}) is None
    assert (
        contract.label_semantics(
            {"name": "x", "description": "semantic-role: kind; semantic-value: nonsense"}
        )
        is None
    )
    assert contract.label_semantics({"name": ""}) is None
    assert contract.label_semantics("not-a-dict") is None


def test_semver_parsing_follows_the_portable_contract() -> None:
    assert contract.parse_semver("1.2.3") == (1, 2, 3, (), ())
    assert contract.parse_semver("1.2.3-rc.1+build.5") == (1, 2, 3, ("rc", "1"), ("build", "5"))
    assert contract.parse_semver("0.0.0") == (0, 0, 0, (), ())
    for invalid in (
        "01.2.3",
        "1.2",
        "1.2.3-",
        "1.2.3+",
        "1.2.3-rc..1",
        "1.2.3-01",
        " 1.2.3",
        42,
    ):
        assert contract.parse_semver(invalid) is None


def test_endpoint_allowlist_accepts_collection_endpoints_only() -> None:
    for endpoint in (
        "user",
        "projects/5/issues/7/discussions",
        "projects/5/merge_requests/7?per_page=100&page=2",
        "projects/5/jobs/9/trace",
        "projects/5/pipelines/3/jobs?per_page=100&page=1",
        "projects/5/releases",
        "projects/5/repository/branches/main",
        "projects/five",
    ):
        assert contract.allowed_endpoint(endpoint) is True
    for endpoint in ("user/extra", "projects/5/merge_requests/7/unknown", "../projects/5"):
        assert contract.allowed_endpoint(endpoint) is False


def test_glab_json_rejects_non_allowlisted_endpoints_before_any_glab_call() -> None:
    with workflow_error("outside the collection allowlist"):
        contract.glab_json("gitlab.example", "projects/1/unknown")
    with workflow_error("outside the collection allowlist"):
        contract.glab_json("GitLab..Example", "user")


def test_trace_parsing_splits_headers_and_applies_range_completeness() -> None:
    response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\ntrace body\n"
    split = contract.split_glab_trace_response(response)
    assert split is not None
    header_bytes, body = split
    assert header_bytes.decode("latin1") == "HTTP/1.1 200 OK\r\nContent-Type: text/plain"
    assert body.decode() == "trace body\n"
    assert contract.parse_glab_trace(response) == ("trace body\n", True)
    partial = b"HTTP/1.1 206\r\ncontent-range: bytes 5-9/20\r\n\r\nabcde"
    assert contract.parse_glab_trace(partial)[1] is False
    whole = b"HTTP/1.1 206\r\nContent-Range: bytes 0-4/5\r\n\r\nabcde"
    assert contract.parse_glab_trace(whole)[1] is True
    _, dropped_complete = contract.parse_glab_trace(b"HTTP/1.1 200\r\n\r\nbody", tail_dropped=True)
    assert dropped_complete is False
    with workflow_error("headers are unavailable"):
        contract.parse_glab_trace(b"garbage")
    with workflow_error("returned HTTP 404"):
        contract.parse_glab_trace(b"HTTP/1.1 404 Not Found\r\n\r\n")
    prefer_lf = contract.split_glab_trace_response(b"HTTP/1.1 200\nX: 1\n\nbody")
    assert prefer_lf is not None
    assert prefer_lf[1].decode() == "body"


def test_trace_excerpt_strips_ansi_redacts_and_keeps_the_bounded_tail() -> None:
    noisy = "\x1b[31merror\x1b[0m: token=abc123\n"
    excerpt = contract.trace_excerpt(noisy, True)
    assert excerpt["complete"] is True
    assert excerpt["truncated"] is False
    assert excerpt["excerpt"] == "error: token=[REDACTED]\n"
    assert excerpt["sha256"] == hashlib.sha256(noisy.encode()).hexdigest()
    big = "x" * (70 * 1024)
    truncated = contract.trace_excerpt(big, True)
    assert truncated["truncated"] is True
    assert isinstance(truncated["excerpt"], str)
    assert len(truncated["excerpt"]) == 64 * 1024
    assert truncated["excerpt"] == big[-64 * 1024 :]
    assert contract.trace_excerpt("short", False)["complete"] is False


def test_select_exact_pipeline_picks_the_newest_pipeline_for_the_head() -> None:
    pipelines: dict[str, object] = {
        "items": [
            {"id": 11, "sha": "aaa"},
            {"id": 17, "sha": "ccc"},
            {"id": 14, "sha": "ccc"},
            {"id": "bogus", "sha": "ccc"},
        ]
    }
    selected = contract.select_exact_pipeline(pipelines, "ccc")
    assert selected is not None
    assert selected["id"] == 17
    assert contract.select_exact_pipeline(pipelines, "zzz") is None
    assert contract.select_exact_pipeline({"items": "nope"}, "ccc") is None


def test_pipeline_jobs_normalize_missing_fields_to_serializable_nulls() -> None:
    job = contract.pipeline_job({"id": 9, "name": "generate build", "status": "success"}, 42, 5)
    assert job == {
        "project_id": 42,
        "pipeline_id": 5,
        "id": 9,
        "name": "generate build",
        "stage": None,
        "status": "success",
        "allow_failure": None,
        "web_url": None,
        "created_at": None,
        "started_at": None,
        "finished_at": None,
        "duration": None,
        "queued_duration": None,
        "failure_reason": None,
    }
    assert json.loads(contract.canonical(job).decode()) == job


def test_pipeline_jobs_preserve_supplied_values_including_false_zero_and_empty_strings() -> None:
    item: dict[str, Any] = {
        "id": 9,
        "name": "lint dockerfiles",
        "stage": "test",
        "status": "failed",
        "allow_failure": False,
        "web_url": "",
        "created_at": CREATED_AT,
        "started_at": None,
        "duration": 0,
        "queued_duration": 0,
        "failure_reason": "script_failure",
    }
    job = contract.pipeline_job(item, 42, 5)
    assert job == {**item, "project_id": 42, "pipeline_id": 5, "finished_at": None}
    assert json.loads(contract.canonical(job).decode()) == job


def test_template_headings_and_chat_labels_follow_the_contract() -> None:
    assert contract.template_headings("## A\nplain\n### B x\n#no\n#### C\n") == [
        "## A",
        "### B x",
        "#### C",
    ]
    en = contract.code_review_chat_labels("en")
    assert en["title"] == "### MR assessment"
    assert en["metadata_values"]["ok"] == "ready"
    ru = contract.code_review_chat_labels("ru")
    assert ru["title"] == "### Оценка MR"
    with workflow_error("review locale must be en or ru"):
        contract.code_review_chat_labels("de")


def test_validate_critic_binds_evidence_and_scope() -> None:
    receipt = critic_payload()
    contract.validate_critic(receipt, DIGEST, DIGEST)
    bare = critic_payload()
    del bare["scope_digest"]
    del bare["target_finding_ids"]
    contract.validate_critic(bare, DIGEST)
    with workflow_error(r"\$\.evidence_digest: must bind the selected evidence digest"):
        contract.validate_critic(receipt, "b" * 64)
    with workflow_error(r"\$\.scope_digest: an incremental receipt must bind"):
        contract.validate_critic({**receipt, "scope_digest": "c" * 64}, DIGEST, DIGEST)
    with workflow_error("independent run identity"):
        contract.validate_critic({**receipt, "run_id": ""}, DIGEST)


def test_validate_decision_accounts_for_findings_and_threads() -> None:
    report = decision_payload()
    receipt = critic_payload()
    contract.validate_decision(report, DIGEST, receipt, "deep", DIGEST, DIGEST)
    with workflow_error("schema-invalid"):
        contract.validate_decision(
            {**report, "verdict": "unknown"}, DIGEST, receipt, "deep", DIGEST, DIGEST
        )
    with workflow_error("does not account for every finding"):
        contract.validate_decision(
            {**report, "responses": []}, DIGEST, receipt, "deep", DIGEST, DIGEST
        )
    no_critic_report = decision_payload()
    del no_critic_report["critic_receipt_digest"]
    no_critic_report["responses"] = [
        response for response in no_critic_report["responses"] if response["id"] == "finding-1"
    ]
    with workflow_error("independent critic receipt"):
        contract.validate_decision({**no_critic_report, "mode": "normal"}, DIGEST, None, "normal")
    with workflow_error("confirmed low-risk scope"):
        contract.validate_decision(
            {**no_critic_report, "mode": "fast", "low_risk": False}, DIGEST, None, "fast"
        )
    contract.validate_decision(
        {**no_critic_report, "mode": "fast", "low_risk": True}, DIGEST, None, "fast"
    )
    with workflow_error("blocking findings prohibit ready"):
        contract.validate_decision(
            {**report, "blocking_findings": True}, DIGEST, receipt, "deep", DIGEST, DIGEST
        )
    with_threads = {
        **report,
        "unresolved_threads": [{"id": "thread:note-1"}],
        "responses": [
            *report["responses"],
            {"id": "thread:note-1", "decision": "reject", "reason": "stale"},
        ],
    }
    contract.validate_decision(with_threads, DIGEST, receipt, "deep", DIGEST, DIGEST)
    bad_namespace = {**with_threads, "unresolved_threads": [{"id": "finding-1"}]}
    with workflow_error("namespace-safe"):
        contract.validate_decision(bad_namespace, DIGEST, receipt, "deep", DIGEST, DIGEST)
    duplicates = {
        **report,
        "findings": [detailed_finding(), detailed_finding(id="finding-2")],
        "responses": [
            *report["responses"],
            {"id": "finding-2", "decision": "accept", "reason": "same"},
        ],
    }
    with workflow_error("structurally duplicate findings"):
        contract.validate_decision(duplicates, DIGEST, receipt, "deep", DIGEST, DIGEST)


def test_finalize_payload_binds_the_evidence_fingerprint_and_validates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_state_home(monkeypatch, tmp_path)
    root = contract.state_directory(
        "code-review",
        {"hostname": "gitlab.example", "project_id": 9, "kind": "merge_requests", "iid": 3},
    )
    evidence = evidence_payload()
    evidence_path, _ = contract.write_artifact(root, "evidence_snapshot", evidence)
    result: dict[str, object] = {"status": "ok", "changed": [], "complete": True, "head_sha": "c"}
    report_payload = contract.finalize_payload(result, evidence_path, evidence, "evidence_snapshot")
    assert report_payload["external_mutations"] is False
    assert report_payload["evidence_kind"] == "evidence_snapshot"
    assert report_payload["evidence_digest"] == sha256_file(evidence_path)
    assert report_payload["evidence_fingerprint_digest"] == contract.digest(
        contract.fingerprint(evidence)
    )
    report_path, _ = contract.write_artifact(root, "finalize_report", report_payload)
    report, report_digest = contract.validate_finalize_report(report_path, evidence_path, evidence)
    assert report["status"] == "ok"
    assert report_digest == sha256_file(report_path)
    stale_path, _ = contract.write_artifact(
        root, "finalize_report", {**report_payload, "status": "stale"}
    )
    with workflow_error("stale, incomplete, or does not bind exact evidence"):
        contract.validate_finalize_report(stale_path, evidence_path, evidence)
    mismatched = evidence_payload()
    mismatched["prepared_at"] = "2026-09-15T00:00:00Z"
    other_path, _ = contract.write_artifact(root, "evidence_snapshot", mismatched)
    with workflow_error("stale, incomplete, or does not bind exact evidence"):
        contract.validate_finalize_report(report_path, other_path, evidence)


def test_evidence_from_root_resolves_pointers_and_legacy_bundles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_state_home(monkeypatch, tmp_path)
    root = contract.state_directory(
        "code-review",
        {"hostname": "gitlab.example", "project_id": 4, "kind": "merge_requests", "iid": 2},
    )
    evidence_path, evidence_digest = contract.write_artifact(
        root, "evidence_snapshot", evidence_payload()
    )
    contract.write_json(
        root / "review-evidence.json",
        {"evidence_path": str(evidence_path), "evidence_digest": evidence_digest},
    )
    source, payload = contract.evidence_from_root(root, "review-evidence.json")
    assert source == evidence_path
    assert payload["profile"] == "code-review"

    contract.write_json(
        root / "current.json",
        {"evidence_path": str(evidence_path), "evidence_digest": evidence_digest},
    )
    assert contract.evidence_from_root(root)[0] == evidence_path

    escaping = json.loads((root / "review-evidence.json").read_text(encoding="utf-8"))
    escaping["evidence_path"] = f"{root.parent}/other/{evidence_digest}.json"
    contract.write_json(root / "review-evidence.json", escaping)
    with workflow_error("escapes collection root"):
        contract.evidence_from_root(root, "review-evidence.json")

    (root / "review-evidence.json").unlink()
    (root / "current.json").unlink()
    with workflow_error("artifact is unavailable"):
        contract.evidence_from_root(root)
    legacy = json.loads(evidence_path.read_text(encoding="utf-8"))
    (root / "bundle.json").write_text(json.dumps(legacy))
    assert contract.evidence_from_root(root)[0] == root / "bundle.json"
    with workflow_error("pointer name is invalid"):
        contract.evidence_from_root(root, "unexpected.json")


def test_write_json_atomically_replaces_pointer_state(tmp_path: Path) -> None:
    pointer = tmp_path / "current.json"
    contract.write_json(pointer, {"a": 1})
    contract.write_json(pointer, {"b": 2})
    assert json.loads(pointer.read_text(encoding="utf-8")) == {"b": 2}
    assert len(list(tmp_path.iterdir())) == 1
    assert mode_of(pointer) == 0o600


def test_fingerprint_keeps_the_canonical_comparison_order() -> None:
    bundle: dict[str, Any] = {
        "profile": "code-review",
        "target": {"iid": 1},
        "head_sha": "c",
        "base_sha": "a",
        "start_sha": "b",
        "object": {"state": "opened"},
        "labels": component(),
        "discussions": component(),
        "changed_files": component(),
        "commits": component(),
        "pipelines": component(),
        "retrieval_complete": True,
        "prepared_at": CREATED_AT,
    }
    value = contract.fingerprint(bundle)
    keys = [
        "target",
        "head_sha",
        "base_sha",
        "start_sha",
        "object",
        "labels",
        "discussions",
        "changed_files",
        "commits",
        "pipelines",
        "retrieval_complete",
    ]
    assert list(value) == keys
    mr_bundle = {**bundle, "profile": "mr-prepare", "project": {"id": 1}}
    assert list(contract.fingerprint(mr_bundle)) == ["mr_project", *keys]
    assert contract.is_digest(contract.digest(value)) is True


def test_issue_link_collection_stops_at_the_complete_100_link_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = tmp_path / "calls.txt"
    install_glab(
        monkeypatch,
        tmp_path,
        "import json\n"
        f"open({str(calls)!r}, 'a').write('GET\\n')\n"
        "print(json.dumps([{'id': i + 1, 'issue_link_id': i + 1001} for i in range(100)]))\n",
    )
    links = contract.paginated("gitlab.example", "projects/5/issues/9/links")
    assert links["complete"] is True
    assert links["pages"] == 1
    assert isinstance(links["items"], list)
    assert len(links["items"]) == 100
    assert calls.read_text(encoding="utf-8") == "GET\n"
    issues = contract.paginated("gitlab.example", "projects/5/issues", max_pages=3)
    assert issues["complete"] is False
    assert issues["errors"] == ["GitLab pagination repeated a page"]


def test_glab_text_streams_a_bounded_trace_through_a_child_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_glab(
        monkeypatch,
        tmp_path,
        "import sys\n"
        "sys.stdout.write('HTTP/1.1 200 OK\\r\\nContent-Type: text/plain\\r\\n\\r\\ntrace body\\n')\n",
    )
    text, complete = contract.glab_text("gitlab.example", "projects/5/jobs/9/trace")
    assert text == "trace body\n"
    assert complete is True


def test_glab_text_reports_a_failed_trace_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_glab(monkeypatch, tmp_path, "import sys\nsys.stderr.write('boom')\nsys.exit(3)\n")
    with workflow_error("failed with status 3"):
        contract.glab_text("gitlab.example", "projects/5/jobs/9/trace")


def test_collect_gathers_evidence_and_finalize_confirms_freshness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_state_home(monkeypatch, tmp_path)
    head_sha, base_sha, start_sha = "c" * 40, "a" * 40, "b" * 40
    diff_refs = {"head_sha": head_sha, "base_sha": base_sha, "start_sha": start_sha}
    responses = {
        "projects/group%2Fproj": {"id": 42},
        "projects/42/labels": [],
        "projects/42/merge_requests/7": {"iid": 7, "diff_refs": diff_refs},
        "projects/42/merge_requests/7/discussions": [],
        "projects/42/merge_requests/7/changes": {
            "overflow": False,
            "changes": [],
            "changes_count": "0",
            "diff_refs": diff_refs,
        },
        "projects/42/merge_requests/7/commits": [{"id": head_sha}],
        "projects/42/merge_requests/7/pipelines": [{"id": 5, "sha": head_sha, "status": "success"}],
        "projects/42/pipelines/5/jobs": [
            {
                "id": 9,
                "name": "generate build",
                "status": "success",
                "allow_failure": False,
                "duration": 0,
            }
        ],
        "projects/42/pipelines/5/bridges": [
            {"id": 10, "name": "child pipeline", "status": "success"}
        ],
    }
    install_glab(
        monkeypatch,
        tmp_path,
        "import json\nimport sys\n"
        "endpoint = sys.argv[-1].split('?')[0]\n"
        f"responses = json.loads({json.dumps(responses)!r})\n"
        "if endpoint not in responses:\n"
        "    sys.stderr.write('unexpected ' + endpoint)\n"
        "    sys.exit(1)\n"
        "sys.stdout.write(json.dumps(responses[endpoint]))\n",
    )
    target = contract.parse_target(
        "https://gitlab.example/group/proj/-/merge_requests/7", {"merge_requests"}
    )
    bundle = contract.collect(target, "code-review")
    assert bundle["retrieval_complete"] is True
    assert bundle["head_sha"] == head_sha
    assert bundle["components_complete"]["pipelines"] is True  # type: ignore[index]
    root = str(bundle["artifact_root"])
    contract.write_json(
        Path(root) / "review-evidence.json",
        {
            "evidence_path": bundle["preview_artifact_path"],
            "evidence_digest": bundle["preview_digest"],
        },
    )
    preview_path = Path(str(bundle["preview_artifact_path"]))
    _, payload = contract.artifact_payload(preview_path, "evidence_snapshot")
    assert payload["profile"] == "code-review"
    assert payload["target"]["project_id"] == 42
    jobs = payload["pipelines"]["items"][0]["job_evidence"]["pipelines"][0]["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["failure_reason"] is None
    assert jobs[0]["allow_failure"] is False
    assert jobs[0]["duration"] == 0
    assert jobs[1]["failure_reason"] is None

    result = contract.finalize(root, "review-evidence.json")
    assert result["status"] == "ok"
    assert result["changed"] == []
    assert result["complete"] is True
    assert result["evidence_digest"] == sha256_file(preview_path)
    assert re.fullmatch(r"[a-f0-9]{64}", str(result["evidence_digest"]))
