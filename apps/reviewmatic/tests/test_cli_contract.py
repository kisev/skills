"""CLI contract: commands, parsing, and exit codes."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from reviewmatic import __version__
from reviewmatic.cli import (
    DEFINITIONS,
    _workflow_namespace,
    all_specs,
    apply_config,
    build_parser,
)

if TYPE_CHECKING:
    import argparse

ROOT = Path(__file__).resolve().parents[1]

# Contract-owned commands are dispatched directly to the shared runtime.
IMPLEMENTED = ("marker-run", "assess-mode", "capabilities", "publication")
# marker-run intercepts its arguments before the parser and does not answer --help.
HELP_SIGNATURES = tuple(
    spec.signature for spec in DEFINITIONS if spec.signature != "marker-run [mutation...]"
)

OPTION_PLACEHOLDERS: dict[str, str] = {
    "--artifact-root": "x",
    "--draft": "x",
    "--url": "https://gitlab.com/group/project/-/merge_requests/1",
    "--project-url": "https://gitlab.com/group/project",
    "--evidence": "x",
    "--repo-root": "x",
    "--context": "x",
    "--decision": "x",
    "--content": "x",
    "--input": "x",
    "--bundle": "x",
    "--report": "x",
    "--finalize-report": "x",
    "--participant": "critic-a",
    "--action": "x",
    "--confirm": "x",
    "--ref": "main",
    "--mode": "fast",
}


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "reviewmatic", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def unimplemented_arguments(signature: str) -> list[str]:
    """Build a parseable invocation: one valid placeholder per declared option."""
    spec = next(definition for definition in DEFINITIONS if definition.signature == signature)
    arguments = signature.split()
    for option in spec.options:
        arguments.append(f"--{option.name}")
        if option.flag:
            continue
        if option.default is not None:
            arguments.append(option.default)
        elif option.choices is not None:
            arguments.append(option.choices[0])
        else:
            arguments.append(OPTION_PLACEHOLDERS.get(f"--{option.name}", "x"))
    return arguments


def test_the_python_command_surface_is_explicit_and_contains_no_terminal_ui() -> None:
    expected = (
        "repair-review",
        "refresh-review",
        "start-review",
        "resume-review",
        "check-review",
        "finish-review",
        "prepare",
        "context",
        "scaffold-review",
        "status",
        "next",
        "template-review",
        "report-review",
        "finalize",
        "record-package",
        "record-input",
        "record-critic",
        "scrub-preview",
        "render-review",
        "record-prose",
        "re-anchor-review",
        "runtime-info",
        "record-run-critic",
        "record-participants",
        "record-ocr-critic",
        "record-arbitration",
        "scope-review",
        "prepare-local",
        "finalize-local",
        "assess-mode",
        "finalize-review",
        "record-artifact",
        "run",
        "replace-artifact",
        "worktree list",
        "publication [mode]",
        "capabilities",
        "marker-run [mutation...]",
    )
    assert tuple(spec.signature for spec in DEFINITIONS) == expected


@pytest.mark.parametrize("signature", HELP_SIGNATURES, ids=lambda value: value.split()[0])
def test_every_subcommand_answers_help(signature: str) -> None:
    result = run_cli(*signature.split(), "--help")
    assert result.returncode == 0, result.stderr
    assert signature.split(maxsplit=1)[0] in result.stdout
    assert "usage:" in result.stdout.lower()


def test_marker_run_intercepts_help_before_the_regular_parser() -> None:
    result = run_cli("marker-run", "--help")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_version_answers_the_package_version() -> None:
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == __version__


def test_bare_invocation_prints_help_without_a_terminal() -> None:
    result = run_cli()
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_missing_command_answers_invalid_command() -> None:
    result = run_cli("--json")
    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "invalid_command"


def test_unknown_command_exits_two() -> None:
    result = run_cli("teleport-review")
    assert result.returncode == 2


def test_missing_required_option_exits_two() -> None:
    result = run_cli("scope-review")
    assert result.returncode == 2
    assert "--artifact-root" in result.stderr


def test_invalid_choice_exits_two() -> None:
    result = run_cli("assess-mode", "--mode", "sideways")
    assert result.returncode == 2


def test_removed_plan_command_is_not_a_terminal_interface() -> None:
    result = run_cli("plan", "--artifact-root", "/tmp/review")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


@pytest.mark.parametrize(
    "signature",
    tuple(spec.signature for spec in DEFINITIONS if spec.signature != "marker-run [mutation...]"),
    ids=lambda value: value.split()[0],
)
def test_business_commands_no_longer_answer_not_implemented(signature: str) -> None:
    """Every exposed business command has a real handler."""
    result = run_cli(*unimplemented_arguments(signature))
    assert result.returncode != 5, (result.stdout, result.stderr)


def test_capabilities_prints_the_contract_envelope() -> None:
    result = run_cli("capabilities")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["profile"] == "code-review"
    assert payload["external_mutations"] is False
    assert isinstance(payload["external_tools"]["git"], bool)


def test_global_capabilities_flag_prints_capabilities() -> None:
    result = run_cli("--capabilities")
    assert result.returncode == 0
    assert json.loads(result.stdout)["profile"] == "code-review"


def test_subcommand_global_flag_prints_capabilities() -> None:
    result = run_cli("assess-mode", "--mode", "fast", "--capabilities")
    assert result.returncode == 0
    assert json.loads(result.stdout)["profile"] == "code-review"


@pytest.mark.parametrize(
    ("arguments", "expected_code", "expected_status"),
    [
        (("--mode", "fast"), 0, "ok"),
        (("--mode", "normal"), 4, "unsupported"),
        (("--mode", "deep", "--critic-available"), 0, "ok"),
    ],
)
def test_assess_mode_contract(
    arguments: tuple[str, ...], expected_code: int, expected_status: str
) -> None:
    result = run_cli("assess-mode", *arguments)
    payload = json.loads(result.stdout)
    assert result.returncode == expected_code, result.stdout
    assert payload["status"] == expected_status
    if expected_code == 0:
        required = arguments[1] in ("normal", "deep")
        assert payload["independent_critic_required"] is required


def test_publication_is_a_blocked_historical_stub() -> None:
    result = run_cli("publication")
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["external_mutations"] is False


def test_publication_capabilities_prints_the_manual_contract() -> None:
    result = run_cli("publication", "--capabilities")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["operations"] == []
    assert payload["publication"] == "manual glab commands"


def test_worktree_without_list_is_invalid() -> None:
    result = run_cli("worktree")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid_command"


def test_worktree_list_answers_the_registry_contract() -> None:
    result = run_cli("worktree", "list")
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "ok"
    assert envelope["items"] == []
    assert envelope["external_mutations"] is False


def test_marker_run_requires_the_mutation_command() -> None:
    result = run_cli("marker-run", "--skill", "reviewmatic", "--action", "a", "--binding", "b" * 64)
    assert result.returncode == 2
    assert "mutation command is required" in result.stderr


def test_marker_run_requires_skill_action_and_binding() -> None:
    result = run_cli("marker-run", "--skill", "reviewmatic")
    assert result.returncode == 2
    assert "--action" in result.stderr


def test_marker_run_rejects_unknown_flags() -> None:
    result = run_cli("marker-run", "--wat", "x")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_configuration_file_must_be_a_json_object(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text("[]", encoding="utf-8")
    result = run_cli("capabilities", "--config", str(config))
    assert result.returncode == 1
    assert "configuration must be a JSON object" in result.stderr


def test_apply_config_respects_cli_env_and_choices() -> None:
    namespace = build_parser().parse_args(["assess-mode", "--mode", "fast"])
    apply_config(namespace, {"mode": "deep", "logLevel": "debug"}, all_specs())
    # CLI-provided values win over the configuration file.
    assert namespace.mode == "fast"
    assert namespace.logLevel == "debug"

    fresh: Any = build_parser().parse_args(["assess-mode", "--mode", "fast"])
    with pytest.raises(Exception, match="invalid configuration value"):
        apply_config(fresh, {"logLevel": "chatty"}, all_specs())

    boolean: Any = build_parser().parse_args(["assess-mode", "--mode", "fast"])
    with pytest.raises(Exception, match="must be boolean"):
        apply_config(boolean, {"json": "yes"}, all_specs())


def test_environment_defaults_resolve_global_options(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    rejected = run_cli("capabilities")
    assert rejected.returncode == 0
    environment = dict(os.environ)
    environment["REVIEWMATIC_CONFIG"] = str(invalid)
    environment["PYTHONPATH"] = str(ROOT / "src")
    applied = subprocess.run(
        [sys.executable, "-m", "reviewmatic", "capabilities"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    # The environment default replaced the missing --config option and was
    # then rejected with the configuration failure contract.
    assert applied.returncode == 1
    assert "Expecting" in applied.stderr

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"logLevel": "debug"}), encoding="utf-8")
    environment["REVIEWMATIC_CONFIG"] = str(valid)
    accepted = subprocess.run(
        [sys.executable, "-m", "reviewmatic", "capabilities"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert accepted.returncode == 0
    assert json.loads(accepted.stdout)["profile"] == "code-review"


def test_global_values_survive_subcommand_parsing() -> None:
    namespace = build_parser().parse_args(
        ["--capabilities", "--log-level", "debug", "assess-mode", "--mode", "fast"]
    )
    assert namespace.capabilities is True
    assert namespace.logLevel == "debug"
    assert namespace.mode == "fast"
    assert namespace.sources == {"capabilities", "logLevel", "mode"}


def test_console_module_entry_point_is_the_cli() -> None:
    namespace: argparse.Namespace = build_parser().parse_args(["capabilities"])
    assert namespace.command == "capabilities"


def test_workflow_namespace_exposes_snake_case_attributes() -> None:
    # workflow.dispatch and workflow.prepared read snake_case attributes.
    namespace = build_parser().parse_args(
        [
            "context",
            "--evidence",
            "evidence.json",
            "--repo-root",
            ".",
            "--review-mode",
            "normal",
            "--locale",
            "ru",
        ]
    )
    workflow_arguments = _workflow_namespace("context", namespace)
    assert workflow_arguments.command == "context"
    assert workflow_arguments.evidence == "evidence.json"
    assert workflow_arguments.repo_root == "."
    assert workflow_arguments.review_mode == "normal"
    assert workflow_arguments.locale == "ru"
    assert workflow_arguments.incremental == "auto"


def test_collected_options_keep_every_occurrence() -> None:
    # _AppendAction must not drop the first value of a collect=True option.
    namespace = build_parser().parse_args(
        ["prepare", "--url", "https://gitlab.example/a/-/merge_requests/1"]
    )
    assert namespace.url == ["https://gitlab.example/a/-/merge_requests/1"]
    repeated = build_parser().parse_args(
        [
            "prepare",
            "--url",
            "https://gitlab.example/a/-/merge_requests/1",
            "--url",
            "https://gitlab.example/b/-/merge_requests/2",
        ]
    )
    assert repeated.url == [
        "https://gitlab.example/a/-/merge_requests/1",
        "https://gitlab.example/b/-/merge_requests/2",
    ]


def test_resolve_install_source_recovers_the_commit_defensively() -> None:
    from reviewmatic.cli import resolve_install_source

    # The real uv form: PEP 610 nests the VCS data in vcs_info.
    uv_git = json.dumps(
        {
            "url": "git+https://github.com/kisev/skills.git@dev#subdirectory=apps/reviewmatic",
            "vcs_info": {"vcs": "git", "commit_id": "3e409c217e94d643f77eb543caab9a2ed4b7288d"},
        }
    )
    assert resolve_install_source(uv_git) == {
        "url": "git+https://github.com/kisev/skills.git@dev#subdirectory=apps/reviewmatic",
        "vcs": "git",
        "commit": "3e409c217e94d643f77eb543caab9a2ed4b7288d",
    }
    # Legacy flat writers record the commit and vcs next to the url.
    legacy_flat = (
        '{"url": "git+https://github.com/kisev/skills.git@dev#subdirectory=apps/reviewmatic",'
        ' "vcs": "git", "commit": "3e409c217e94d643f77eb543caab9a2ed4b7288d"}'
    )
    assert resolve_install_source(legacy_flat)["commit"] == (
        "3e409c217e94d643f77eb543caab9a2ed4b7288d"
    )
    assert resolve_install_source(legacy_flat)["vcs"] == "git"
    pinned_in_url = (
        '{"url": "git+https://github.com/kisev/skills.git'
        '@df46265aabbccdd00112233445566778899aabbb#subdirectory=apps/reviewmatic"}'
    )
    assert (
        resolve_install_source(pinned_in_url)["commit"]
        == "df46265aabbccdd00112233445566778899aabbb"
    )
    registry = '{"url": "https://files.pythonhosted.org/packages/reviewmatic-1.0.0.tar.gz"}'
    assert resolve_install_source(registry) == {
        "url": "https://files.pythonhosted.org/packages/reviewmatic-1.0.0.tar.gz",
        "vcs": None,
        "commit": "unknown",
    }
    for honest_unknown in (None, "not json", "[1, 2]", '{"url": 7}', '{"vcs_info": "git"}'):
        assert resolve_install_source(honest_unknown)["commit"] == "unknown"


def test_runtime_info_reports_the_version_and_install_commit() -> None:
    result = run_cli("runtime-info")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["version"] == __version__
    assert payload["external_mutations"] is False
    assert payload["commit"] == "unknown" or re.fullmatch(r"[0-9a-f]{40}", payload["commit"])
