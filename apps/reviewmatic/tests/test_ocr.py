"""The OCR engine integration: version gate, parallel runs, parsing, compare."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from reviewmatic import ocr
from reviewmatic.portable.portable_gitlab import contract

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ocr"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fake_ocr(tmp_path: Path, *, version: str = "1.13.6") -> Path:
    """A fake ocr CLI that handles version, review, and session compare."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "ocr"
    payload = json.dumps(json.loads(fixture("review.json")))
    compare = json.dumps(json.loads(fixture("compare-groups.json")))
    script.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  version)\n"
        f"    echo 'open-code-review v{version} (abc) linux/amd64'\n"
        "    exit 0 ;;\n"
        "  review)\n"
        "    out=''\n"
        "    while [ $# -gt 0 ]; do\n"
        "      if [ \"$1\" = '--output' ]; then out=$2; shift; fi\n"
        "      shift\n"
        "    done\n"
        f"    printf '%s' '{payload}' > \"$out\"\n"
        "    exit 0 ;;\n"
        "  session)\n"
        f"    printf '%s' '{compare}'\n"
        "    exit 0 ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return bin_dir


def reviewers() -> list[dict[str, str]]:
    return [
        {"alias": "fast", "provider": "openai", "model": "gpt-5", "effort": "medium"},
        {"alias": "deep", "provider": "anthropic", "model": "claude-opus-5", "effort": "high"},
    ]


def test_the_installed_version_is_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = fake_ocr(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert ocr.installed_version() == (1, 13, 6)
    assert ocr.version_check()["status"] == "ok"


def test_an_old_version_stops_with_the_upgrade_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = fake_ocr(tmp_path, version="1.12.9")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    check = ocr.version_check()
    assert check["status"] == "old"
    assert "npm install -g @alibaba-group/open-code-review@latest" in str(check["instruction"])


def test_a_missing_engine_stops_with_the_install_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    check = ocr.version_check()
    assert check["status"] == "missing"
    assert "npm install -g" in str(check["instruction"])


def test_review_parsing_is_tolerant() -> None:
    parsed = ocr.parse_review(fixture("review.json"))
    assert parsed["session_id"] == "sess-123"
    assert parsed["run_id"] == "run-9"
    assert parsed["comments_count"] == 2
    assert parsed["comments"][0]["severity"] == "high"
    assert parsed["comments"][1]["severity"] == "low"


def test_review_parsing_drops_empty_comments() -> None:
    parsed = ocr.parse_review(fixture("review-partial.json"))
    assert parsed["session_id"] is None
    assert parsed["comments_count"] == 1
    assert parsed["comments"][0]["start_line"] is None


def test_review_parsing_rejects_non_json() -> None:
    with pytest.raises(contract.WorkflowError, match="valid JSON"):
        ocr.parse_review("not json")


def test_parallel_runs_write_one_output_per_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = fake_ocr(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    background = tmp_path / "background.md"
    background.write_text("# background\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    result = ocr.run_reviews(
        repo=str(tmp_path),
        from_ref="b" * 40,
        to_ref="a" * 40,
        background=background,
        reviewers=reviewers(),
        output_dir=output_dir,
    )
    assert result["status"] == "ok"
    assert result["parallel"] is True
    assert {run["alias"] for run in result["runs"]} == {"fast", "deep"}
    assert all(run["comments_count"] == 2 for run in result["runs"])
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "ocr-deep.json",
        "ocr-fast.json",
    ]


def test_an_oversized_background_is_refused_before_spawning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = fake_ocr(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    background = tmp_path / "background.md"
    background.write_text("x" * 8001, encoding="utf-8")
    with pytest.raises(contract.WorkflowError, match="8000"):
        ocr.run_reviews(
            repo=str(tmp_path),
            from_ref="b",
            to_ref="a",
            background=background,
            reviewers=reviewers()[:1],
            output_dir=tmp_path / "out",
        )


def test_a_resume_applies_to_exactly_one_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = fake_ocr(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    background = tmp_path / "background.md"
    background.write_text("# background\n", encoding="utf-8")
    with pytest.raises(contract.WorkflowError, match="exactly one"):
        ocr.run_reviews(
            repo=str(tmp_path),
            from_ref="b",
            to_ref="a",
            background=background,
            reviewers=reviewers(),
            output_dir=tmp_path / "out",
            resume="sess-1",
        )


def test_a_single_reviewer_resume_reaches_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.log"
    script = bin_dir / "ocr"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {log}\n"
        "if [ \"$1\" = 'version' ]; then echo 'open-code-review v1.13.6'; exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    background = tmp_path / "background.md"
    background.write_text("# background\n", encoding="utf-8")
    ocr.run_reviews(
        repo=str(tmp_path),
        from_ref="b",
        to_ref="a",
        background=background,
        reviewers=reviewers()[:1],
        output_dir=tmp_path / "out",
        resume="sess-1",
    )
    assert "--resume sess-1" in log.read_text(encoding="utf-8")


def test_compare_normalizes_named_groups() -> None:
    groups = ocr.normalize_compare(json.loads(fixture("compare-groups.json")))
    assert {key: len(items) for key, items in groups.items()} == {
        "new": 1,
        "persisting": 1,
        "resolved": 1,
        "not_reviewed": 1,
    }


def test_compare_normalizes_a_status_list() -> None:
    groups = ocr.normalize_compare(json.loads(fixture("compare-list.json")))
    assert [item["path"] for item in groups["new"]] == ["a.py"]
    assert [item["path"] for item in groups["persisting"]] == ["b.py"]
    assert [item["path"] for item in groups["resolved"]] == ["c.py"]
    assert [item["path"] for item in groups["not_reviewed"]] == ["d.py"]


def test_compare_runs_the_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = fake_ocr(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    result = ocr.compare("sess-1", "sess-2", repo=str(tmp_path))
    assert result["counts"] == {"new": 1, "persisting": 1, "resolved": 1, "not_reviewed": 1}
    assert result["external_mutations"] is False


def test_compare_rejects_unknown_shapes() -> None:
    assert ocr.normalize_compare("nonsense") == {
        "new": [],
        "persisting": [],
        "resolved": [],
        "not_reviewed": [],
    }


def test_run_records_carry_no_finding_without_a_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = fake_ocr(tmp_path)
    # A run that exits non-zero is reported, never silently accepted.
    script = bin_dir / "ocr"
    script.write_text(
        "#!/bin/sh\nif [ \"$1\" = 'version' ]; then echo 'open-code-review v1.13.6'; exit 0; fi\n"
        "echo 'provider failed' >&2\nexit 2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    background = tmp_path / "background.md"
    background.write_text("# background\n", encoding="utf-8")
    result = ocr.run_reviews(
        repo=str(tmp_path),
        from_ref="b",
        to_ref="a",
        background=background,
        reviewers=reviewers()[:1],
        output_dir=tmp_path / "out",
    )
    assert result["status"] == "failed"
    assert result["runs"][0]["exit_code"] == 2
    assert result["runs"][0]["comments"] == []
