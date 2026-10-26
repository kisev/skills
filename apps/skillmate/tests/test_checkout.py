"""Checkout source tests: validation, build step, and dev reading — offline."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from skillmate.checkout import CheckoutSource
from skillmate.distribution import DistributionError

if TYPE_CHECKING:
    from collections.abc import Callable

FIXTURE = Path(__file__).parent / "fixtures" / "distribution"


def _checkout(tmp_path: Path) -> Path:
    """A minimal working-tree shape with the built distribution hidden inside."""
    checkout = tmp_path / "checkout"
    (checkout / "scripts").mkdir(parents=True)
    (checkout / "skills").mkdir()
    (checkout / "scripts" / "build_distribution.py").write_text("# stub\n")
    return checkout


def _fake_build(fixture: Path) -> Callable[[list[str], Path], None]:
    def run(arguments: list[str], cwd: Path) -> None:
        assert arguments == ["task", "distribution:build"]
        target = cwd / ".build" / "packages" / "skills"
        shutil.copytree(fixture, target, dirs_exist_ok=True)

    return run


def test_checkout_source_reads_built_content_as_dev(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    source = CheckoutSource(checkout=checkout, run=_fake_build(FIXTURE))
    distribution, built = source.resolve()
    assert set(distribution.skills) == {"alpha", "beta"}
    assert built.base == checkout / ".build" / "packages" / "skills"
    assert built.archive(distribution.skills["beta"]).files[0].data.startswith(b"---")


def test_checkout_source_rejects_a_foreign_directory(tmp_path: Path) -> None:
    source = CheckoutSource(checkout=tmp_path / "elsewhere", run=_fake_build(FIXTURE))
    with pytest.raises(DistributionError, match="not a checkout"):
        source.resolve()


def test_checkout_source_reports_a_failed_build(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)

    def run(arguments: list[str], cwd: Path) -> None:
        pass

    source = CheckoutSource(checkout=checkout, run=run)
    with pytest.raises(DistributionError, match="produced no distribution"):
        source.resolve()


def test_default_runner_surfaces_task_absence(tmp_path: Path) -> None:
    from skillmate.checkout import _run_task

    with pytest.raises(DistributionError, match="requires `task`"):
        _run_task(["skillmate-missing-task"], tmp_path)
