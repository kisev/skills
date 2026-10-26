"""Safety-model golden tests: preview, confirmation, ownership, drift, collision.

Each test pins one scenario from the skillmate specification: no write
without confirmation, foreign files untouched, user drift never silently
overwritten, removal of owned files only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from skillmate.safety import (
    SafetyError,
    build_install_plan,
    build_remove_plan,
    execute,
    load_ownership,
)

if TYPE_CHECKING:
    from pathlib import Path

DESIRED = {
    "skills/humanize/SKILL.md": b"---\nname: humanize\n---\nBody v1.\n",
    "commands/humanize.md": b"# /humanize\n",
}


def _install(root: Path, desired: dict[str, bytes] | None = None, version: str = "1.0.0") -> None:
    plan = build_install_plan(
        root, DESIRED if desired is None else desired, load_ownership(root), version, "distribution"
    )
    execute(plan, confirmed=True)


def test_unconfirmed_plan_writes_nothing(tmp_path: Path) -> None:
    plan = build_install_plan(tmp_path, DESIRED, None, "1.0.0", "distribution")
    with pytest.raises(SafetyError, match="unconfirmed"):
        execute(plan, confirmed=False)
    assert not (tmp_path / "skills").exists()
    assert not (tmp_path / ".skillmate").exists()


def test_confirmed_install_writes_files_and_manifest(tmp_path: Path) -> None:
    _install(tmp_path)
    assert (tmp_path / "skills/humanize/SKILL.md").read_bytes() == DESIRED[
        "skills/humanize/SKILL.md"
    ]
    ownership = load_ownership(tmp_path)
    assert ownership is not None
    assert ownership.distribution_version == "1.0.0"
    assert set(ownership.by_path()) == set(DESIRED)


def test_reinstall_of_identical_content_is_a_noop(tmp_path: Path) -> None:
    _install(tmp_path)
    plan = build_install_plan(tmp_path, DESIRED, load_ownership(tmp_path), "1.0.0", "distribution")
    assert plan.empty
    assert plan.steps == ()


def test_foreign_file_is_reported_and_untouched(tmp_path: Path) -> None:
    foreign = tmp_path / "skills/humanize/SKILL.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"user content")
    plan = build_install_plan(tmp_path, DESIRED, None, "1.0.0", "distribution")
    assert plan.collisions == ("skills/humanize/SKILL.md",)
    with pytest.raises(SafetyError, match="collisions must be resolved"):
        execute(plan, confirmed=True)
    assert foreign.read_bytes() == b"user content"
    assert not (tmp_path / "commands/humanize.md").exists()


def test_user_drift_is_reported_and_never_overwritten(tmp_path: Path) -> None:
    _install(tmp_path)
    drifted = tmp_path / "skills/humanize/SKILL.md"
    drifted.write_bytes(b"user edited")
    updated = dict(DESIRED)
    updated["skills/humanize/SKILL.md"] = b"---\nname: humanize\n---\nBody v2.\n"
    updated["commands/humanize.md"] = b"# /humanize v2\n"
    plan = build_install_plan(tmp_path, updated, load_ownership(tmp_path), "2.0.0", "distribution")
    assert plan.drifted == ("skills/humanize/SKILL.md",)
    execute(plan, confirmed=True)
    assert drifted.read_bytes() == b"user edited"
    assert (tmp_path / "commands/humanize.md").read_bytes() == b"# /humanize v2\n"
    recorded = load_ownership(tmp_path)
    assert recorded is not None
    assert "skills/humanize/SKILL.md" not in recorded.by_path()


def test_removal_takes_only_owned_files(tmp_path: Path) -> None:
    _install(tmp_path)
    foreign = tmp_path / "skills/other/SKILL.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"foreign")
    plan = build_remove_plan(tmp_path, load_ownership(tmp_path))  # type: ignore[arg-type]
    execute(plan, confirmed=True)
    assert not (tmp_path / "skills/humanize").exists()
    assert not (tmp_path / "commands/humanize.md").exists()
    assert foreign.read_bytes() == b"foreign"
    assert load_ownership(tmp_path) is None


def test_drifted_removal_requires_explicit_confirmation(tmp_path: Path) -> None:
    _install(tmp_path)
    drifted = tmp_path / "skills/humanize/SKILL.md"
    drifted.write_bytes(b"user edited")
    plan = build_remove_plan(tmp_path, load_ownership(tmp_path))  # type: ignore[arg-type]
    assert plan.drifted == ("skills/humanize/SKILL.md",)
    execute(plan, confirmed=True)
    assert drifted.read_bytes() == b"user edited"
    assert load_ownership(tmp_path) is not None
    plan = build_remove_plan(tmp_path, load_ownership(tmp_path))  # type: ignore[arg-type]
    execute(plan, confirmed=True, confirm_drift=True)
    assert not drifted.exists()
    assert load_ownership(tmp_path) is None


def test_missing_owned_files_are_reported_as_missing(tmp_path: Path) -> None:
    _install(tmp_path)
    (tmp_path / "commands/humanize.md").unlink()
    plan = build_remove_plan(tmp_path, load_ownership(tmp_path))  # type: ignore[arg-type]
    assert plan.missing == ("commands/humanize.md",)


def test_paths_outside_the_host_directory_are_refused(tmp_path: Path) -> None:
    with pytest.raises(SafetyError, match="outside the host directory"):
        build_install_plan(tmp_path, {"../escape": b"x"}, None, "1.0.0", "distribution")


def test_plan_preview_lists_every_change(tmp_path: Path) -> None:
    plan = build_install_plan(tmp_path, DESIRED, None, "1.0.0", "distribution", notices=("n1",))
    text = plan.preview()
    assert "skills/humanize/SKILL.md" in text
    assert "commands/humanize.md" in text
    assert "notice: n1" in text
    machine = plan.machine()
    assert machine["schema"] == "skillmate-plan/v1"
    assert len(machine["steps"]) == 2  # type: ignore[arg-type]
