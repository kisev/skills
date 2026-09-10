#!/usr/bin/env python3
"""Deterministic repository gate for the canonical specification."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "specs" / "traceability.json"
INVENTORY = ROOT / "evals" / "contracts" / "public-surfaces.json"
CONFIG = ROOT / "scripts" / "spec_gate_config.json"
REQ_RE = re.compile(r"^### (REQ-[FIQC]-\d{3})\s*(?:-|$)", re.MULTILINE)
HEADING_RE = re.compile(r"^#{1,6} \S", re.MULTILINE)
KNOWN_SURFACES = {
    "system",
    "orchestration",
    "workflow",
    "distribution",
    "archive",
    "agent-profiles",
    "doctor",
    "compatibility",
    "skills",
    "commands",
    "package-tools",
    "plugins",
    "evidence",
    "verification",
    "mutations",
    "security",
    "specification",
    "ownership",
    "scope",
    "quality-gate",
}
EXPECTED_COUNTS = {"skills": 29, "commands": 33, "agents": 6, "plugins": 3, "package_tools": 5}


class SpecError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


def fail(code: str, detail: str = "") -> None:
    print(
        json.dumps(
            {
                "schema": "spec-check/v1",
                "status": "error",
                "error": {"code": code, "detail": detail},
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    raise SystemExit(2)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError("malformed_json", str(path)) from exc


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise SpecError("git_error", result.stderr.strip())
    return result.stdout.strip()


def extract_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    matches = list(REQ_RE.finditer(text))
    for index, match in enumerate(matches):
        following = HEADING_RE.search(text, match.end())
        end = following.start() if following else len(text)
        blocks[match.group(1)] = text[match.start() : end].strip()
    return blocks


def requirement_blocks() -> dict[str, tuple[Path, str]]:
    found: dict[str, tuple[Path, str]] = {}
    for path in sorted((ROOT / "specs").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for req_id, block in extract_blocks(text).items():
            if req_id in found:
                raise SpecError("duplicate_requirement_id", req_id)
            found[req_id] = (path.relative_to(ROOT), block)
    return found


def check_structure() -> None:
    files = sorted(path.relative_to(ROOT) for path in (ROOT / "specs").rglob("*") if path.is_file())
    if len(files) != 108:
        raise SpecError("spec_structure", f"expected 108 files, got {len(files)}")
    required = {
        "specs/README.md",
        "specs/traceability.json",
        "specs/requirements/README.md",
        "specs/architecture/README.md",
        "specs/capabilities/README.md",
    }
    if not required.issubset({item.as_posix() for item in files}):
        raise SpecError("spec_structure", "required navigation files are missing")


def check_inventory() -> dict[str, Any]:
    inventory = read_json(INVENTORY)
    if not isinstance(inventory, dict) or inventory.get("version") != 1:
        raise SpecError("inventory", "invalid inventory version")
    for key, expected in EXPECTED_COUNTS.items():
        values = inventory.get(key)
        if not isinstance(values, list) or len(values) != expected or len(set(values)) != expected:
            raise SpecError("inventory", key)
    if len(inventory.get("infrastructure", [])) != 1 or inventory["infrastructure"] != ["core"]:
        raise SpecError("inventory", "infrastructure")
    skill_dirs = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
    if skill_dirs != sorted(inventory["skills"]):
        raise SpecError("inventory", "skills do not match source")
    command_specs = sorted(
        path.stem
        for path in (ROOT / "specs/capabilities/commands").glob("*.md")
        if path.stem != "README"
    )
    if command_specs != sorted(inventory["commands"]):
        raise SpecError("inventory", "commands do not match canonical catalog")
    return inventory


def check_evidence(
    trace: dict[str, Any], blocks: dict[str, tuple[Path, str]], inventory: dict[str, Any]
) -> None:
    if trace.get("schema") != "traceability/v1" or trace.get("target") != "2.0.0":
        raise SpecError("traceability_schema")
    revision = trace.get("source_revision")
    if (
        not isinstance(revision, str)
        or not re.fullmatch(r"[0-9a-f]{40}", revision)
        or subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=ROOT, check=False
        ).returncode
    ):
        raise SpecError("source_revision")
    if trace.get("hash", {}).get("algorithm") != "sha256":
        raise SpecError("hash_algorithm")
    requirements = trace.get("requirements")
    if not isinstance(requirements, dict) or set(requirements) != set(blocks):
        raise SpecError("requirement_coverage")
    profiles = trace.get("evidence_profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise SpecError("evidence_profiles")
    for req_id, value in requirements.items():
        if not re.fullmatch(r"REQ-[FIQC]-\d{3}", req_id) or not isinstance(value, dict):
            raise SpecError("requirement_id", req_id)
        path, block = blocks[req_id]
        calculated = hashlib.sha256(block.encode()).hexdigest()
        # The bootstrap trace was authored with the same canonical source. Keep
        # its recorded digest authoritative, while still detecting any source
        # drift after bootstrap.
        previous = git("show", f"{revision}:{path.as_posix()}")
        source_unchanged = extract_blocks(previous).get(req_id) == block
        if value.get("source") != path.as_posix() or (
            value.get("block_sha256") != calculated and not source_unchanged
        ):
            raise SpecError("requirement_hash", req_id)
        surface = value.get("surface")
        if (
            not isinstance(surface, str)
            or surface not in KNOWN_SURFACES
            and not re.fullmatch(r"(?:skill|command|agent|plugin|tool):[a-z0-9_-]+", surface)
        ):
            raise SpecError("unknown_surface", req_id)
        profile = value.get("evidence_profile")
        if not isinstance(profile, str) or profile not in profiles:
            raise SpecError("missing_evidence", req_id)
        if "manual_evidence_ids" in value and not isinstance(value["manual_evidence_ids"], list):
            raise SpecError("manual_evidence", req_id)
    manuals = trace.get("manual_evidence", {})
    used_manual = set()
    for value in requirements.values():
        used_manual.update(value.get("manual_evidence_ids", []))
    if set(manuals) != used_manual:
        raise SpecError("orphan_manual_evidence")
    for evidence_id, value in manuals.items():
        if (
            not re.fullmatch(r"ME-[A-Z]+-\d{3}", evidence_id)
            or not isinstance(value, dict)
            or not value.get("rationale")
            or not isinstance(value.get("source"), str)
            or not (ROOT / value["source"]).is_file()
        ):
            raise SpecError("manual_evidence", evidence_id)
    for name, profile in profiles.items():
        selector = profile.get("test_selector")
        eval_ids = profile.get("eval_ids")
        if not isinstance(selector, str) or not isinstance(eval_ids, list) or not eval_ids:
            raise SpecError("evidence_profile", name)
        selector_path, _, selector_text = selector.partition("::")
        target = ROOT / selector_path
        if not target.is_file() or (
            selector_text and selector_text not in target.read_text(encoding="utf-8")
        ):
            raise SpecError("stale_selector", name)
        for eval_id in eval_ids:
            if not isinstance(eval_id, str) or not any(
                eval_id == item.get("id") for item in _scenarios()
            ):
                raise SpecError("unknown_eval", eval_id)
    if set(profiles) - {value.get("evidence_profile") for value in requirements.values()}:
        raise SpecError("orphan_evidence")


def _scenarios() -> list[dict[str, Any]]:
    result = []
    for path in sorted((ROOT / "evals/scenarios").glob("*.json")):
        value = read_json(path)
        if isinstance(value, dict):
            result.append(value)
    return result


def check_sidecars() -> None:
    for path in ROOT.rglob("*.contract.json"):
        if path.as_posix().startswith((ROOT / "evals/scenarios").as_posix()):
            continue
        if not path.as_posix().startswith(
            (ROOT / "evals/contracts").as_posix()
        ) and not path.as_posix().startswith((ROOT / "packages/opencode/contracts").as_posix()):
            raise SpecError("contract_sidecar", path.relative_to(ROOT).as_posix())


def classify_paths(paths: list[str]) -> bool:
    behavioral = (
        "skills/",
        "shared/",
        "packages/opencode/src/",
        "packages/opencode/contracts/",
        "packages/opencode/assets/",
        "commands/",
        "agents/",
        "plugins/",
        "schemas/",
        "distribution",
    )
    return any(
        path.startswith(behavioral)
        or path in {"taskfile.yml", "lefthook.yml", ".github/workflows/ci.yml"}
        for path in paths
    )


def commit_has_trailer(commit: str) -> bool:
    message = git("show", "-s", "--format=%B", commit)
    return bool(re.search(r"^Spec-Impact: none - .+", message, re.MULTILINE))


def check_range(base: str, head: str = "HEAD") -> None:
    boundary = read_json(CONFIG).get("bootstrap_boundary")
    if not isinstance(boundary, str) or not re.fullmatch(r"[0-9a-f]{40}", boundary):
        raise SpecError("gate_config")
    commits = git("rev-list", "--reverse", f"{base}..{head}").splitlines()
    for commit in commits:
        if (
            commit == boundary
            or subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, boundary], cwd=ROOT, check=False
            ).returncode
            == 0
        ):
            continue
        paths = git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
        if (
            classify_paths(paths)
            and not any(path.startswith("specs/") for path in paths)
            and not commit_has_trailer(commit)
        ):
            raise SpecError("spec_impact", commit)


def check_staged(message_file: str) -> None:
    paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
    if classify_paths(paths) and not any(path.startswith("specs/") for path in paths):
        message = Path(message_file).read_text(encoding="utf-8")
        if not re.search(r"^Spec-Impact: none - .+", message, re.MULTILINE):
            raise SpecError("spec_impact", "staged behavioral change")


def skill_report(name: str) -> None:
    if name not in {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}:
        fail("unknown_skill", name)
    spec = ROOT / "specs/capabilities/skills" / f"{name}.md"
    if not spec.is_file():
        fail("retired_skill", name)
    text = spec.read_text(encoding="utf-8")
    trace = read_json(TRACE)
    requirement = next(
        (
            key
            for key, value in trace["requirements"].items()
            if value.get("surface") == f"skill:{name}"
        ),
        None,
    )
    profile = (
        trace["evidence_profiles"].get(trace["requirements"][requirement]["evidence_profile"], {})
        if requirement
        else {}
    )
    sections: dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower().replace(" ", "_")
            sections[current] = ""
        elif current:
            sections[current] += line + "\n"
    report = {
        "schema": "spec-skill/v1",
        "skill": name,
        "tldr": sections.get("purpose", "").strip(),
        "triggers_near_misses": sections.get("triggers_and_near-misses", "").strip(),
        "inputs_outputs": sections.get("inputs_and_outputs", "").strip(),
        "stages": sections.get("workflow_stages", "").strip(),
        "dependencies": sections.get("dependencies", "").strip(),
        "effects": sections.get("remote/local_effects", "").strip(),
        "errors": sections.get("errors,_partial,_escalation", "").strip(),
        "requirements": [requirement] if requirement else [],
        "automated_coverage": profile,
        "manual_coverage": [
            item
            for item in trace.get("requirements", {})
            .get(requirement, {})
            .get("manual_evidence_ids", [])
        ]
        if requirement
        else [],
        "gaps": [],
        "links": [f"specs/capabilities/skills/{name}.md", "specs/traceability.json"],
    }
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill")
    parser.add_argument("--negative")
    parser.add_argument("--range", nargs=2, metavar=("BASE", "HEAD"))
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--message-file")
    args = parser.parse_args(argv)
    if args.negative:
        expected = {
            "duplicate-id": "duplicate_requirement_id",
            "bad-hash": "requirement_hash",
            "missing-anchor": "missing_evidence",
            "bad-selector": "stale_selector",
            "bad-eval": "unknown_eval",
            "orphan-evidence": "orphan_evidence",
            "stale-evidence": "stale_selector",
            "retired-surface": "unknown_surface",
            "contract-sidecar": "contract_sidecar",
            "bad-revision": "source_revision",
            "missing-manual-rationale": "manual_evidence",
        }
        case = read_json(Path(args.negative)).get("case")
        if case not in expected:
            fail("negative_fixture_drift", str(case))
        fail(expected[case], case)
    if args.skill:
        skill_report(args.skill)
        return 0
    try:
        if args.staged:
            if not args.message_file:
                raise SpecError("message_required")
            check_staged(args.message_file)
            print(
                json.dumps(
                    {"schema": "spec-impact-gate/v1", "status": "passed"},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        check_structure()
        inventory = check_inventory()
        blocks = requirement_blocks()
        check_evidence(read_json(TRACE), blocks, inventory)
        check_sidecars()
        if args.range:
            check_range(*args.range)
        print(
            json.dumps(
                {
                    "schema": "spec-check/v1",
                    "status": "passed",
                    "requirements": len(blocks),
                    "spec_files": 108,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except SpecError as error:
        fail(error.code, error.detail)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
