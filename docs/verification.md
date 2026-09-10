# Verification

[Русская версия](ru/verification.md)

## Release 2.0.0

The release is reproducible from one exact commit: the annotated `v2.0.0` tag,
the `@kisev/skills-opencode@2.0.0` package, and the GitHub Release must identify
the same commit. Portable skills are installed directly from that immutable Git
tag with `npx --yes skills@1.5.23`; use `--agent opencode` or `--agent codex` and
pin the tag URL for an exact migration from `v1.2.0`.

The migration inventory records renamed and removed skills, command/plugin
retirements, and an empty alias set. `reconcile` preserves retired exact-owned
assets in a private content-addressed archive as `archive-pending`; it does not
purge archive entries, and modified or user-owned files remain conflicts. The
package tool `route` remains available, while the `/route` slash command and old
action/mode aliases are not shipped.

The optional OpenCode package targets `>=1.18.29 <1.19.0`, is tested against
`1.18.29` and `1.18.30`, and requires Node.js 22+. Portable skills do not depend
on that package. Known limitations remain documented: Mattermost parity is
incomplete, runtime state and `doctor` need further hardening, stateful plugins
are opt-in, and live evaluation is outside the ordinary quality gate.

Stage 20 verifies the `2.0.0` public contract without invoking a model, network,
provider, or credential. `task eval:check` validates the committed scenario corpus
and runs every deterministic assertion; it is included by `task check`.

The corpus has four scenarios for each skill: English trigger, English near-miss,
Russian trigger, and Russian near-miss. The trigger and near-miss pairs keep the
same expected structured outcome and mutation boundary. Scenario IDs and digests
are content-addressed and duplicate prompts are rejected by the corpus tests.

Deterministic contracts cover all 29 skills, 33 command adapters, 6 agents, 3
selectable plugins, 5 package tools, and the core infrastructure plugin. The
committed negative corpus covers duplicate identity, digest drift, missing pairs,
unknown surfaces, path escapes, malformed results, incomplete budgets, secret
leakage, unsupported hosts, and stale package inventory.

The compatibility inventory in `evals/contracts/opencode-compatibility.json` pins
the minimum OpenCode `1.18.29` and the current `1.18.30` release to
`>=1.18.29 <1.19.0`. Build, registration, config, installer, and agent discovery
checks use both slots and require no credentials.

Live evaluation is never part of `task check`. It requires explicit
`--trusted-live`, host, model, timeout, token and cost budgets, and an output path.
No model or baseline is selected by default, and untrusted CI does not receive
credentials or run the live gate.

Generated runtime copies and build outputs are checked for parity. A clean
temporary checkout must retain an unchanged `git status` after build and check;
declared committed copies are tracked, while temporary outputs remain ignored.
