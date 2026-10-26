"""The dev-only checkout source: unpublished working-tree content.

The checkout source runs the checkout's own build (``task
distribution:build``, which materializes skills and packs the
distribution) and reads the produced directory. It never falls back to
the remote distribution: a checkout that fails to build is an error.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from skillmate.distribution import Distribution, DistributionError, LocalSource

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _run_task(arguments: list[str], cwd: Path) -> None:
    try:
        completed = subprocess.run(arguments, cwd=cwd, check=False, capture_output=True)  # noqa: S603
    except FileNotFoundError as error:
        raise DistributionError(
            "the checkout source requires `task` (via mise) on PATH to build the working tree"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:500]
        raise DistributionError(f"checkout build failed ({' '.join(arguments)}): {detail}")


@dataclass(frozen=True)
class CheckoutSource:
    """A working tree of this repository, built on demand."""

    checkout: Path
    run: Callable[[list[str], Path], None] = _run_task
    build_command: tuple[str, ...] = ("task", "distribution:build")

    def validate(self) -> None:
        """Fail loudly unless the path looks like a checkout of this repository."""
        marker = self.checkout / "scripts" / "build_distribution.py"
        sources = self.checkout / "skills"
        if not marker.is_file() or not sources.is_dir():
            raise DistributionError(
                f"{self.checkout} is not a checkout of this repository "
                "(scripts/build_distribution.py and skills/ are missing)"
            )

    def build(self) -> LocalSource:
        """Build the checkout and return its distribution directory source."""
        self.validate()
        self.run(list(self.build_command), self.checkout)
        built = self.checkout / ".build" / "packages" / "skills"
        if not (built / "index.json").is_file():
            raise DistributionError(
                f"checkout build produced no distribution at {built / 'index.json'}"
            )
        return LocalSource(built)

    def resolve(self) -> tuple[Distribution, LocalSource]:
        """Return the built distribution and its directory source, dev-stamped."""
        source = self.build()
        return source.index(), source
