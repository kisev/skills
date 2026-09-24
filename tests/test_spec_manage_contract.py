from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/spec-manage"


def section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n\n(?P<body>.*?)(?=\n## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, heading
    return match.group("body")


def test_language_authority_and_extension_contract_has_one_structural_owner() -> None:
    contract = (SKILL / "references/canonical-contract.md").read_text(encoding="utf-8")

    language = section(contract, "Canonical language")
    authority = section(contract, "Normative authority by mode")
    extensions = section(contract, "Minimum structure and extensions")
    assert {
        f"`{mode}`" for mode in ("spec-init", "spec-onboard", "spec-update", "spec-audit")
    } <= set(re.findall(r"`spec-[a-z]+`", language))
    assert re.findall(r"^- `(spec-[a-z]+)`:", authority, re.MULTILINE) == [
        "spec-init",
        "spec-onboard",
        "spec-update",
        "spec-audit",
    ]
    assert "`specs/capabilities/`" in extensions
    assert "roadmap, task, plan, proposal" in extensions


def test_language_decisions_precede_writes_and_conflicts_remain_explicit() -> None:
    workflow = (SKILL / "references/workflow.md").read_text(encoding="utf-8")
    canonical = (SKILL / "references/canonical-contract.md").read_text(encoding="utf-8")
    for mode in ("spec-init", "spec-onboard"):
        body = re.search(
            rf"^### `{mode}`\n\n(?P<body>.*?)(?=\n### |\Z)",
            workflow,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert body is not None
        language_position = body.group("body").index("explicit project-language choice")
        write_position = body.group("body").index("create")
        assert language_position < write_position
    assert "If the prose is mixed, absent, or otherwise ambiguous, stop and ask" in " ".join(
        canonical.split()
    )
    assert "obtain a user decision" in canonical
