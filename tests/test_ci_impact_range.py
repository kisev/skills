from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.resolve_spec_impact import RangeError, load_event, resolve_range


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/ci-events"
FAILED_TAG_RUN = "https://github.com/kisev/skills/actions/runs/34496801895"


def fixture(name: str) -> dict[str, object]:
    return load_event(FIXTURES / f"{name}.json")


def test_pull_request_range_uses_exact_base_and_head() -> None:
    result = resolve_range(fixture("pull-request"), "pull_request")
    assert result["base"] == "f40e15d76257e7fadc127cad2449d5918571f166"
    assert result["head"] == "88fa466589bede791c6caa7780a7a98caf89e767"
    assert result["kind"] == "pull_request"


def test_normal_branch_push_range_uses_before_and_after() -> None:
    result = resolve_range(fixture("branch-push"), "push")
    assert result["base"] == "8f4452c67ec33739dc987d47971dfea39e5d0f84"
    assert result["head"] == "88fa466589bede791c6caa7780a7a98caf89e767"
    assert result["kind"] == "branch"


def test_zero_before_branch_push_uses_bootstrap_boundary() -> None:
    result = resolve_range(fixture("branch-bootstrap"), "push")
    assert result["base"] == "a1e48be947aca9873eb09885599a1139cee6bc25"
    assert result["head"] == "88fa466589bede791c6caa7780a7a98caf89e767"
    assert result["kind"] == "branch_bootstrap"


def test_tag_push_uses_first_parent_and_never_zero_sha() -> None:
    result = resolve_range(fixture("tag-push"), "push")
    assert result["base"] == "8f4452c67ec33739dc987d47971dfea39e5d0f84"
    assert result["head"] == "88fa466589bede791c6caa7780a7a98caf89e767"
    assert ZERO_SHA not in result.values()
    assert FAILED_TAG_RUN.endswith("34496801895")


def test_annotated_tag_event_uses_github_commit_not_tag_object() -> None:
    event = fixture("tag-push")
    event["after"] = subprocess.check_output(
        ["git", "rev-parse", "v2.0.0"], cwd=ROOT, text=True
    ).strip()
    result = resolve_range(
        event,
        "push",
        github_sha="88fa466589bede791c6caa7780a7a98caf89e767",
    )
    assert result["base"] == "8f4452c67ec33739dc987d47971dfea39e5d0f84"
    assert result["head"] == "88fa466589bede791c6caa7780a7a98caf89e767"


def test_v2_0_0_regression_captures_zero_before_invalid_range() -> None:
    event = fixture("tag-push")
    before = str(event["before"])
    assert before == ZERO_SHA
    result = subprocess.run(
        [
            "git",
            "rev-list",
            "--reverse",
            f"{before}..88fa466589bede791c6caa7780a7a98caf89e767",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert FAILED_TAG_RUN == "https://github.com/kisev/skills/actions/runs/34496801895"


def test_tag_push_rejects_unreachable_head(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    (tmp_path / "file").write_text("main\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "file"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "main"], check=True)
    main_sha = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    (tmp_path / "file").write_text("unreachable\n")
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qam", "unreachable"], check=True)
    unreachable_sha = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "-C", str(tmp_path), "update-ref", "refs/remotes/origin/main", main_sha], check=True
    )
    event = fixture("tag-unreachable")
    event["after"] = unreachable_sha
    with pytest.raises(RangeError, match="tag_unreachable"):
        resolve_range(event, "push", tmp_path)


def test_malformed_and_unknown_events_fail_closed_with_stable_json() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/resolve_spec_impact.py",
            "--event-file",
            str(FIXTURES / "malformed.json"),
            "--event-name",
            "push",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "error": {"code": "malformed_head"},
        "schema": "spec-impact-range/v1",
        "status": "error",
    }
    with pytest.raises(RangeError, match="unknown_event"):
        resolve_range(fixture("branch-push"), "workflow_dispatch")


def test_root_commit_tag_fails_closed(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    (tmp_path / "file").write_text("root\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "file"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "root"], check=True)
    root_sha = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "-C", str(tmp_path), "update-ref", "refs/remotes/origin/main", root_sha], check=True
    )
    event = fixture("root-commit")
    event["after"] = root_sha
    with pytest.raises(RangeError, match="root_commit"):
        resolve_range(event, "push", tmp_path)


ZERO_SHA = "0" * 40
