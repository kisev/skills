# Changelog register

The quality register for one changelog item in a release MR. `release-prepare`
applies it while authoring items; `release-review` applies the same register and
its done-when checklist while reviewing them.

## Item register

- One item covers one user-visible behavior change and stays at or below about
  200 characters of body text. Move version, compatibility, and migration
  statements to their own sections instead of stretching the item.
- Describe the behavior a user can point to, not the mechanics that produced
  it. Name the visible surface (CLI command, page, setting, API, document);
  omit internal component, store, and route names unless users see them.
  Translate a mechanical change into its user-visible symptom, or group it
  under a plain reliability item, or drop it.
- State the behavior directly. Do not frame an item as "X, not Y": the
  contrasting tail dismisses an alternative the reader never claimed and reads
  as marketing. Keep a contrast only when it corrects a belief the release
  notes themselves created, such as a documented previous behavior of a fix.
- Fold every follow-up commit into the item of the component MR it belongs to:
  a fix, revert, or follow-up commit never receives its own item. Verify the
  folded item still states the final behavior the MR delivers.
- Reachability per artifact: an item may claim only the surfaces that the
  shipped artifact actually reaches. The archive, the npm package, the Pages
  deployment, and each app under `apps/` carry different surfaces; before an
  item lists a surface, confirm the change is reachable in that artifact, and
  omit the item from artifacts that do not receive it.
- Write the bold heading as a name of the change in 2-6 words, then state the
  behavior in one or two plain sentences.

## Example

Weak:

> **Cache layer.** The sync engine now persists local refs first instead of
> rewriting the payload store, making the app faster and more reliable.

Strong:

> **Attachment cache.** Reopening a chat with attachments shows them
> immediately, without re-downloading files received in the current session.

The weak item names mechanics ("local refs", "payload store"), claims a
generic payoff ("faster and more reliable"), and contrasts instead of
stating. The strong item names the surface, the moment the user notices, and
one concrete consequence.

## Done-when checklist

Run the checklist top to bottom before finalizing or approving a changelog:

- [ ] Every item is at or below about 200 characters and names one change.
- [ ] Every item states user-visible behavior; a reader can point to it in the
  product.
- [ ] No item frames its content as "X, not Y".
- [ ] Every follow-up commit is folded into its component MR item, and each
  item states the final behavior.
- [ ] Every claimed surface is reachable in the artifact this changelog
  ships with; items for unreached surfaces are removed.
- [ ] Every heading is 2-6 words and names the change.
- [ ] Items are ordered by user impact, with breaking changes first.
- [ ] Empty sections are removed and compatibility and migration sections are
  present even when no action is required.

A changelog is done when every item passes every check; a release review
reports each failing check as a confirmed finding with the minimum fix.

## Source

The register adapts the changelog-authoring discipline from
`openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f` (MIT,
Copyright (c) 2025 Bohdan Triapitsyn); the pinned revision is recorded in each
skill's frontmatter `metadata.inspired-by` field. This register is an original
adaptation of that idea for this collection, not a copy of the upstream text.
