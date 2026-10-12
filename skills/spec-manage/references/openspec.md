# OpenSpec coexistence

Apply this map only when the target project uses OpenSpec (`openspec/` exists); otherwise ignore it. OpenSpec owns `openspec/specs/` (per-capability `spec.md` with RFC-2119 `SHALL` requirements and `WHEN`/`THEN` scenarios, plain Markdown) and the change lifecycle under `openspec/changes/` (`proposal.md`, `specs/` deltas with `ADDED`/`MODIFIED`/`REMOVED` requirements, `design.md`, `tasks.md`, slash commands like `/opsx:propose`, `/opsx:archive`). This skill complements OpenSpec where it is structurally weak; it never reproduces OpenSpec's own surfaces.

## Territory

- `openspec/specs/` is the OpenSpec project's source of truth; change proposals, deltas, archive merging, their `openspec validate` checker, and their agent integration are their mechanisms. Do not duplicate any of them, and never create a parallel `specs/` tree next to a project.
- This skill's only writes inside `openspec/` are ADR journal files under `openspec/decisions/` (below). Everything else this map provides is interview, analysis, audit, or a prepared change handed back to OpenSpec's own flow.
- `openspec/decisions/` is not an OpenSpec artifact: their validators scan `specs/` and `changes/` only. After the first journal writes, run the project's own structural check (for example `openspec validate --all`) and report it `passed` or `failed` as ordinary evidence.
- Our canonical-tree contracts never attach to `openspec/`: the 19-file skeleton, `REQ-*` requirement IDs, append-only `specs/` lifecycle records, and the declared canonical language are rules for our trees, not theirs.

| Service | Target artifacts | Rule |
| - | - | - |
| Proposal gate | before or with `/opsx:propose` | Interview and acceptance bar (below) |
| ADR bridge | `openspec/decisions/*` | Append-only journal (below) |
| Spec quality audit | `openspec/specs/**/spec.md` | Read-only audit (below) |
| Post-archive consolidation | one new OpenSpec change | Compacted capability spec via their delta flow (below) |
| NFR domain check | `openspec/specs/**/spec.md` | Missing-domain proposal (below) |

## Proposal gate

When the user is about to run `/opsx:propose`, or asks this skill to shape a proposal before it exists, apply the interview areas in `references/interviewing.md` first, then hold the gate:

- Ask the validation-versus-verification question explicitly: which claims change observable behavior (candidate `SHALL` requirements for the delta spec), and which describe only how a candidate will be checked (scenarios, tests, CI)? An unobservable claim never becomes a `SHALL`; a verification-only claim never becomes a requirement.
- Raise the acceptance bar before the proposal is written: every proposed behavior needs at least one concrete `WHEN`/`THEN` scenario that fails without the change; a proposal with no scenario-worthy behavior declares zero spec deltas instead.
- Deliver the conclusions as content the user enters into `/opsx:propose`. This skill never runs `openspec` lifecycle commands and never writes `proposal.md`, `design.md`, or `tasks.md`.

## ADR bridge

`openspec/decisions/` is an append-only decision journal in this skill's ADR canon (`references/adr.md`, file shape `templates/adr.md`): one ADR is one file, `ADR-NNNN-short-title.md`, indexed under `openspec/decisions/README.md`. Numbering is append-only: a new number exceeds every previously assigned number, and never fill a gap, renumber, reuse an ID, or delete a record.

- Record only architecturally significant decisions, per `references/adr.md`; a bugfix, rename, or trivial implementation stays unrecorded.
- When a change is archived, its `design.md` decisions typically die with the archive folder. Offer to carry the significant accepted ones into `ADR-NNNN` entries at that moment, before the change folder moves; if the user declines, report what was proposed.
- For a replacement, create a new ADR, set the old one `superseded`, and keep its ID, title, date, concise original summary, supersession reason, and the two-way link exactly as `references/adr.md` requires.
- An entry names its source change so the archived `design.md` remains traceable. Decisions state context, decision, and consequences; requirements stay in OpenSpec specs.

## Spec quality audit

Their validator is structural only: delta shape, sections, and archived task ticks. It assesses neither meaning, nor consistency, nor drift from implementation. When the user asks this skill to assess OpenSpec specifications — for example after several archives, before a release, or on request — audit read-only and report confirmed findings with severity, exact capability path, consequence, and minimum fix, ordered per `references/auditing.md` before its drift protocol:

- One fact, one place: a behavior stated twice inside a capability, a `SHALL` contradicted within the same file, or contract detail leaking from one capability into another is a defect; name the single owner and flag the copy for its owning domain's next delta.
- Duplication between domains: identical or overlapping requirements in different capability specs with no declared owner.
- Bounded unknowns: a claim the available evidence cannot confirm is reported truthfully as unverifiable, not as a confirmed defect, and never as an invented implementation fact.
- Language and strength: unbounded or unmeasurable wording (`fast`, `reasonable`, `up-to-date`) without a concrete bound; misapplied RFC-2119 (`MUST`, `SHOULD`, `MAY` used interchangeably or unintentionally); a scenario missing for a `SHALL`.
- Never edit `openspec/specs/` from an audit; fixes land through their future change deltas.

## Post-archive consolidation

OpenSpec grows capability specs organically without an upper bound: archives keep adding requirements, and overlap accumulates. When a capability `spec.md` has grown beyond compact review or its requirements contradict each other, prepare a consolidation change instead of editing the live spec:

- Create one OpenSpec change whose delta spec carries the consolidated target state; removed or merged requirements appear in `REMOVED`/`MODIFIED` sections with their new unified form. Merge duplicates, drop withdrawn history, restore missing scenarios for surviving `SHALL` requirements, and keep one requirement per fact.
- Let `openspec archive` merge the delta exactly as it merges any change; this skill never rewrites or renumbers `openspec/specs/` by hand.
- Consolidation never invents new behavior; it only merges, compacts, and restates conditions already decided.
- Report `Consolidation: required` with the named capability and planned change, or `Consolidation: not required` with a reason.

## NFR domain check

Capability specs often declare only functional behavior. When auditing or shaping a proposal, check whether the specs cover security (subjects, trust boundaries, secrets, sensitive data), compatibility (existing clients, stored data, surviving upgrades), and performance or reliability (measured bounds, rates, recovery after partial failure). Propose each missing domain as required for the next OpenSpec change before unrelated features ship on top of it — not as a decorative section. A proposal that silently adds behavior touching an uncovered domain stops at the proposal gate until the domain is stated.
