# Verification

[Русская версия](ru/verification.md)

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
