#!/usr/bin/env python3
"""Generate the committed stage-20 deterministic contract corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "scenarios"
SKILLS = json.loads((ROOT / "evals/contracts/public-surfaces.json").read_text())["skills"]

# Per-skill prompt overrides keep contract scenarios realistic where the generic
# routing template would be misleading, together with the revision that marks
# the content change. Keys are (skill, kind, locale) and (skill, kind).
PROMPT_OVERRIDES: dict[tuple[str, str, str], str] = {
    ("humanize", "trigger", "ru"): (
        'Примени навык humanize к абзацу из заметки о релизе: "Мы не просто '
        'ускорили поиск, а переписали его с нуля. Это настоящий прорыв!"'
    ),
    ("humanize", "trigger", "en"): (
        "Apply the humanize skill to this release-note paragraph: \"We didn't "
        "just speed up search, we rewrote it from scratch. This is a real "
        'breakthrough!"'
    ),
    ("humanize", "near-miss", "ru"): (
        "Отрефактори функцию format_price в src/pricing.py и обнови её docstring."
    ),
    ("humanize", "near-miss", "en"): (
        "Refactor the format_price function in src/pricing.py and update its docstring."
    ),
}
REVISION_OVERRIDES: dict[tuple[str, str], int] = {
    ("humanize", "trigger"): 2,
    ("humanize", "near-miss"): 2,
}
EXTRA_INVARIANTS: dict[tuple[str, str], list[dict[str, str]]] = {
    ("humanize", "trigger"): [
        {
            "id": "humanize-explicit-activation",
            "path": "skills/humanize/SKILL.source.md",
            "contains": "only on an explicit invocation",
        }
    ],
    ("humanize", "near-miss"): [
        {
            "id": "humanize-explicit-activation",
            "path": "skills/humanize/SKILL.source.md",
            "contains": "never activates this skill by itself",
        }
    ],
}


def digest(value: dict[str, object]) -> str:
    content = {key: item for key, item in value.items() if key != "digest"}
    encoded = json.dumps(content, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def scenario(
    identifier: str,
    pair: str,
    locale: str,
    kind: str,
    prompt: str,
    selected: list[str],
    not_selected: list[str],
    surface: str,
    path: str,
    boundary: str,
    revision: int = 1,
    extra_invariants: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "eval-scenario/v1",
        "id": identifier,
        "revision": revision,
        "locale": locale,
        "pair_id": None if kind == "deterministic" else pair,
        "kind": kind,
        "surface": surface,
        "host": "any",
        "input": {"prompt": prompt, "fixture": {"selected": selected}},
        "expected": {
            "selected": selected,
            "not_selected": not_selected,
            "structured_outcome": "contract-passed" if selected else "safe-escalation",
            "mutation_boundary": boundary,
        },
        "invariants": [
            {"id": f"{pair or identifier}.source", "path": path},
            *(extra_invariants or []),
        ],
        "sandbox": {"network": False, "user_config": False, "writes": "sandbox-only"},
        "budgets": {"timeout_seconds": 20, "max_tokens": 1000, "max_cost": 1},
    }
    value["digest"] = digest(value)
    return value


def write(value: dict[str, object]) -> None:
    path = OUT / f"{value['id']}.json"
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n")


def main() -> None:
    for name in SKILLS:
        for kind in ("trigger", "near-miss"):
            pair = f"stage20.skill.{name}.{kind}"
            expected = [f"skill:{name}"] if kind == "trigger" else []
            rejected = [] if kind == "trigger" else [f"skill:{name}"]
            for locale, language in (("en", "English"), ("ru", "Russian")):
                suffix = "" if locale == "ru" else ".en"
                wording = "Select" if language == "English" else "Выбери"
                prompt = PROMPT_OVERRIDES.get(
                    (name, kind, locale),
                    (
                        f"{wording} the {name} skill for its exact contract scenario."
                        if locale == "en"
                        else f"Выбери навык {name} для его точного контрактного сценария."
                    ),
                )
                if kind == "near-miss" and (name, kind, locale) not in PROMPT_OVERRIDES:
                    prompt = (
                        f"{language}: this is intentionally unrelated to {name}; do not route it to that skill."
                        if locale == "en"
                        else f"Русский: это намеренно не относится к навыку {name}; не направляй запрос в этот навык."
                    )
                write(
                    scenario(
                        f"{pair}{suffix}",
                        pair,
                        locale,
                        kind,
                        prompt,
                        expected,
                        rejected,
                        "skill",
                        f".build/skills/{name}/SKILL.md",
                        "no-writes",
                        revision=REVISION_OVERRIDES.get((name, kind), 1),
                        extra_invariants=EXTRA_INVARIANTS.get((name, kind)),
                    )
                )

    surfaces = {
        "command": (
            json.loads((ROOT / "evals/contracts/public-surfaces.json").read_text())["commands"],
            "packages/agentomatic/src/registry.ts",
            "adapter-only",
        ),
        "agent": (
            json.loads((ROOT / "evals/contracts/public-surfaces.json").read_text())["agents"],
            "packages/agentomatic/assets/agents/{name}.md",
            "host-owned-or-card-bound",
        ),
        "plugin": (
            json.loads((ROOT / "evals/contracts/public-surfaces.json").read_text())["plugins"],
            "packages/agentomatic/src/plugins/{name}.ts",
            "enabled-option-only",
        ),
        "package-tool": (
            json.loads((ROOT / "evals/contracts/public-surfaces.json").read_text())[
                "package_tools"
            ],
            "packages/agentomatic/src/index.ts",
            "phase-and-confirmation-bound",
        ),
        "infrastructure": (["core"], "packages/agentomatic/src/index.ts", "host-owned-runtime"),
    }
    for surface, (names, path, boundary) in surfaces.items():
        for name in names:
            concrete = path.format(name=name.replace("_", "-"))
            identifier = f"stage20.{surface}.{name.replace('_', '-')}.contract"
            write(
                scenario(
                    identifier,
                    "",
                    "neutral",
                    "deterministic",
                    f"Verify {surface} {name} contract.",
                    [f"{surface}:{name}"],
                    [],
                    surface,
                    concrete,
                    boundary,
                )
            )


if __name__ == "__main__":
    main()
