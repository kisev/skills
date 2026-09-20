from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs"
REQUIREMENT_HEADING = re.compile(r"^### (REQ-[A-Z]+-[0-9]{3}) - \S.*$")
ADR_FILENAME = re.compile(r"(?P<number>[0-9]{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")


def test_canonical_requirement_ids_are_unique() -> None:
    locations: dict[str, tuple[Path, int]] = {}
    duplicates: dict[str, list[str]] = {}

    for path in sorted(SPECS.rglob("*.md")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.startswith("### REQ-"):
                continue
            match = REQUIREMENT_HEADING.match(line)
            assert match is not None, f"{path.relative_to(ROOT)}:{line_number}"
            requirement = match.group(1)
            location = (path.relative_to(ROOT), line_number)
            previous = locations.setdefault(requirement, location)
            if previous != location:
                duplicates.setdefault(requirement, [f"{previous[0]}:{previous[1]}"]).append(
                    f"{location[0]}:{location[1]}"
                )

    assert locations
    assert duplicates == {}


def test_canonical_adr_filenames_match_headings() -> None:
    directory = SPECS / "architecture" / "09-architecture-decisions"
    paths = sorted(path for path in directory.glob("*.md") if path.name != "README.md")
    identifiers: set[str] = set()

    assert paths
    for path in paths:
        match = ADR_FILENAME.fullmatch(path.name)
        assert match is not None, path.relative_to(ROOT)
        identifier = f"ADR-{match.group('number')}"
        heading = path.read_text(encoding="utf-8").splitlines()[0]
        assert heading.startswith(f"# {identifier}:"), path.relative_to(ROOT)
        assert identifier not in identifiers
        identifiers.add(identifier)
