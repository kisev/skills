"""Unit contract of the live-run runner: profile pinning, the environment
allowlist, engine adapter argv, declarative assertions, and the fault
injection of blocked commands — all against fakes, with no model calls."""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from scripts import live_runner


def _fake_token() -> str:
    return "glpat-" + secrets.token_urlsafe(30)


PROFILE: dict[str, object] = {
    "engine": "ccr",
    "ccr_profile": "skills-tests-claude",
    "budgets": {"timeout_seconds": 60},
}
PROFILE_STRINGS = {key: str(value) for key, value in PROFILE.items()}


def test_allowlisted_env_withholds_credentials_by_construction() -> None:
    env = live_runner.allowlisted_env(
        {
            "PATH": "/bin",
            "HOME": "/home/x",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "XDG_DATA_HOME": "/tmp/xdg",
            "SECRET_TOKEN": _fake_token(),
            "MM_READ": "leak",
            "ANTHROPIC_API_KEY": "sk-xyz",
        }
    )
    assert env == {
        "PATH": "/bin",
        "HOME": "/home/x",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "XDG_DATA_HOME": "/tmp/xdg",
    }


def test_ccr_adapter_argv_and_claude_parse() -> None:
    argv = live_runner._ccr_start(PROFILE_STRINGS, "do it", ["Bash(ln:*)"])
    assert argv == [
        "ccr",
        "skills-tests-claude",
        "--",
        "-p",
        "do it",
        "--output-format",
        "json",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        "Bash(ln:*)",
    ]
    assert live_runner._ccr_start(PROFILE_STRINGS, "do it", [])[-1] == "acceptEdits"
    text, session = live_runner._claude_parse(json.dumps({"result": "done", "session_id": "ses_1"}))
    assert (text, session) == ("done", "ses_1")
    assert live_runner._claude_parse("plain words") == ("plain words", None)


def test_profile_validation_rejects_unknown_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"engine": "wb", "ccr_profile": "x"}), encoding="utf-8")
    monkeypatch.setattr(live_runner, "PROFILE_PATH", path)
    with pytest.raises(live_runner.LiveRunError, match="unknown engine 'wb'"):
        live_runner.load_profile()


def test_assertion_evaluation_over_staged_fixture(tmp_path: Path) -> None:
    workdir = tmp_path / "fixture"
    (workdir / "packages" / "ts-widget").mkdir(parents=True)
    (workdir / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (workdir / "CLAUDE.md").symlink_to("AGENTS.md")
    diverged = workdir / "packages" / "ts-widget" / "CLAUDE.md"
    diverged.write_text("# unique\n", encoding="utf-8")
    before = live_runner.snapshot(workdir)
    after = dict(before)
    checks = [
        {"type": "file_exists", "path": "AGENTS.md"},
        {"type": "is_symlink", "path": "CLAUDE.md", "target": "AGENTS.md"},
        {"type": "hash_unchanged", "path": "packages/ts-widget/CLAUDE.md"},
        {"type": "is_regular_file", "path": "CLAUDE.md"},
        {"type": "output_mentions", "pattern": "claude", "flags": "i"},
    ]
    results = live_runner.evaluate_assertions(checks, workdir, before, after, "see Claude.md")
    by_id = {item["id"]: item["status"] for item in results}
    assert by_id["file_exists:AGENTS.md"] == "passed"
    assert by_id["is_symlink:CLAUDE.md"] == "passed"
    assert by_id["hash_unchanged:packages/ts-widget/CLAUDE.md"] == "passed"
    assert by_id["is_regular_file:CLAUDE.md"] == "failed"
    assert by_id["output_mentions:4"] == "passed"


def _stage_scenario_tree(base: Path) -> None:
    scenario = base / "evals" / "live" / "mirror" / "fixture"
    scenario.mkdir(parents=True)
    (scenario / "root.txt").write_text("fixture\n", encoding="utf-8")
    manifest = base / "evals" / "live" / "mirror"
    (manifest / "scenario.json").write_text(
        json.dumps(
            {
                "schema": "live-scenario/v1",
                "skill": "agents-md",
                "prompt": "prompt.txt",
                "variants": {
                    "default": {"assertions": "assertions.json"},
                    "no-symlink": {
                        "assertions": "assertions-no-symlink.json",
                        "block_commands": ["ln"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (manifest / "prompt.txt").write_text("set up instructions\n", encoding="utf-8")
    (manifest / "assertions.json").write_text(
        json.dumps(
            [
                {"type": "file_exists", "path": "AGENTS.md"},
                {"type": "is_symlink", "path": "CLAUDE.md", "target": "AGENTS.md"},
                {"type": "output_mentions", "pattern": "CLAUDE", "flags": "i"},
            ]
        ),
        encoding="utf-8",
    )
    (manifest / "assertions-no-symlink.json").write_text(
        json.dumps(
            [
                {"type": "file_exists", "path": "AGENTS.md"},
                {"type": "is_regular_file", "path": "CLAUDE.md"},
                {"type": "content_equals_sibling", "path": "CLAUDE.md", "sibling": "AGENTS.md"},
            ]
        ),
        encoding="utf-8",
    )
    skill = base / "build" / "skills" / "agents-md"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("skill\n", encoding="utf-8")


def _fake_engine(symlink: bool) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(
        argv: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, **_: object
    ) -> subprocess.CompletedProcess[str]:
        assert cwd is not None and env is not None
        assert "SECRET_TOKEN" not in env, "credentials must not ride along"
        if argv[:2] == ["ccr", "skills-tests-claude"] and "blocked-bin" in env["PATH"]:
            wrapper = Path(env["PATH"].split(":")[0]) / "ln"
            assert wrapper.stat().st_mode & stat.S_IXUSR
        agents = cwd / "AGENTS.md"
        agents.write_text("# agents\n", encoding="utf-8")
        mirror = cwd / "CLAUDE.md"
        if symlink:
            mirror.symlink_to("AGENTS.md")
        else:
            mirror.write_text(agents.read_text(encoding="utf-8"), encoding="utf-8")
        assert (cwd / ".agents" / "skills" / "agents-md" / "SKILL.md").is_file()
        assert (cwd / ".git").is_dir()
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps({"result": "done; CLAUDE.md mirror created", "session_id": "s1"}),
            "",
        )

    return run


def test_run_scenario_default_variant_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_scenario_tree(tmp_path)
    monkeypatch.setattr(live_runner, "LIVE_DIR", tmp_path / "evals" / "live")
    monkeypatch.setattr(live_runner, "BUILD_SKILLS", tmp_path / "build" / "skills")
    monkeypatch.setattr(live_runner, "REPORT_ROOT", tmp_path / "reports")
    monkeypatch.setenv("SECRET_TOKEN", _fake_token())
    report = live_runner.run_scenario("mirror", "default", PROFILE, runner=_fake_engine(True))
    assert report["verdict"] == "PASS"
    assert report["engine"] == "ccr" and report["engine_profile"] == "skills-tests-claude"
    assert Path(report["report_dir"], "report.json").is_file()
    assert all(item["status"] == "passed" for item in report["assertions"])


def test_run_scenario_timeout_is_reported_with_partial_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_scenario_tree(tmp_path)
    monkeypatch.setattr(live_runner, "LIVE_DIR", tmp_path / "evals" / "live")
    monkeypatch.setattr(live_runner, "BUILD_SKILLS", tmp_path / "build" / "skills")
    monkeypatch.setattr(live_runner, "REPORT_ROOT", tmp_path / "reports")

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, timeout=1)

    report = live_runner.run_scenario("mirror", "default", PROFILE, runner=runner)
    assert report["verdict"] == "TIMEOUT"
    assert report["error"] == ""
    transcript = Path(report["transcript"]).read_text(encoding="utf-8")
    assert "run exceeded its timeout budget" in transcript
    assert Path(report["report_dir"], "report.json").is_file()


def test_host_state_skips_missing_directories(tmp_path: Path) -> None:
    assert live_runner.host_state([tmp_path / "absent"]) == {}


def test_run_scenario_records_host_drift_under_the_engine_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_home = tmp_path / "profiles" / "skills-tests-claude"
    engine_home.mkdir(parents=True)
    (engine_home / "session.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(live_runner, "_host_watch", lambda profile: [engine_home])
    _stage_scenario_tree(tmp_path)
    monkeypatch.setattr(live_runner, "LIVE_DIR", tmp_path / "evals" / "live")
    monkeypatch.setattr(live_runner, "BUILD_SKILLS", tmp_path / "build" / "skills")
    monkeypatch.setattr(live_runner, "REPORT_ROOT", tmp_path / "reports")
    inner = _fake_engine(True)

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        (engine_home / "session.json").write_text('{"dirty": true}', encoding="utf-8")
        (engine_home / "history.jsonl").write_text("line\n", encoding="utf-8")
        return inner(argv, **kwargs)

    report = live_runner.run_scenario("mirror", "default", PROFILE, runner=runner)
    assert report["verdict"] == "PASS"
    assert any(path.endswith("session.json") for path in report["host_drift"])
    assert any(path.endswith("history.jsonl") for path in report["host_drift"])


def test_run_all_aggregates_verdicts_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reports = {
        "a": {"scenario": "a", "variant": "default", "verdict": "PASS"},
        "b": {"scenario": "b", "variant": "default", "verdict": "FAIL"},
    }
    monkeypatch.setattr(live_runner, "list_scenarios", lambda: ["a", "b"])
    monkeypatch.setattr(live_runner, "load_profile", lambda: PROFILE)
    monkeypatch.setattr(
        live_runner, "run_scenario", lambda name, variant, profile, runner=None: reports[name]
    )
    assert live_runner.main(["run", "--all"]) == 1
    out = capsys.readouterr().out
    assert "a: PASS" in out and "b: FAIL" in out and "sweep: 1/2 passed" in out
    assert live_runner.main(["run", "--scenario", "a", "--all"]) == 2


def test_run_scenario_blocked_commands_prepend_fault_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_scenario_tree(tmp_path)
    monkeypatch.setattr(live_runner, "LIVE_DIR", tmp_path / "evals" / "live")
    monkeypatch.setattr(live_runner, "BUILD_SKILLS", tmp_path / "build" / "skills")
    monkeypatch.setattr(live_runner, "REPORT_ROOT", tmp_path / "reports")
    report = live_runner.run_scenario("mirror", "no-symlink", PROFILE, runner=_fake_engine(False))
    assert report["verdict"] == "PASS"
    assert report["variant"] == "no-symlink"


def test_scenario_format_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage_scenario_tree(tmp_path)
    live = tmp_path / "evals" / "live"
    monkeypatch.setattr(live_runner, "LIVE_DIR", live)
    (live / "broken" / "fixture").mkdir(parents=True)
    (live / "broken" / "scenario.json").write_text(
        json.dumps({"schema": "wrong", "prompt": "p.txt"}), encoding="utf-8"
    )
    assert live_runner.list_scenarios() == ["broken", "mirror"]
    with pytest.raises(live_runner.LiveRunError, match="expected schema"):
        live_runner.load_scenario("broken")
    with pytest.raises(live_runner.LiveRunError, match="not found"):
        live_runner.load_scenario("absent")


def test_snapshot_marks_symlinks_and_ignores_vcs_and_skills(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".agents" / "skills").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("a\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").symlink_to("AGENTS.md")
    snap = live_runner.snapshot(tmp_path)
    assert snap == {
        "AGENTS.md": f"file:{snap['AGENTS.md'].split(':')[1]}",
        "CLAUDE.md": "symlink:AGENTS.md",
    }
    assert not any(key.startswith((".git", ".agents")) for key in snap)


def test_report_transcript_is_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_runner, "REPORT_ROOT", tmp_path / "reports")
    report = {"schema": live_runner.RUN_SCHEMA, "scenario": "x", "variant": "default"}
    run_dir = live_runner.write_report(
        report, "token glpat-abcdef123456 here", "bearer abc123 tail"
    )
    text = (run_dir / "transcript.txt").read_text(encoding="utf-8")
    assert "glpat-abcdef123456" not in text and "abc123" not in text
    assert "[REDACTED]" in text
    saved = SimpleNamespace(**json.loads((run_dir / "report.json").read_text(encoding="utf-8")))
    assert saved.transcript.endswith("transcript.txt")
    assert os.path.isabs(saved.transcript)
