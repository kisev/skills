# Necessity and completion doctrine

Shared assessment rules for review candidates, remedies, and follow-up work.
Apply them before promoting any candidate and before judging completion.

## Necessity before implementation choices

For each candidate, establish the agreed requirement, the reachable scenario and
its assumptions, the user consequence, the relation to the latest changes, and
the proportionate minimum remedy. Separate an unmet requirement or regression
from optional hardening, pre-existing debt, and a new feature. Reproduction or
fault injection alone proves neither practical reachability, priority, nor
blocker status. Use risk and evidence to calibrate severity and effort; do not
raise either to justify doing more work. Report optional hardening and scope
expansion separately from acceptance blockers.

Explain this assessment before asking how to implement a remedy. Recommend
accepting a limitation, deferring work, or rejecting the candidate when
justified. Do not call all remaining fixes mandatory merely because they
appeared in a review, and treat a request to discuss every finding as approval
to discuss, not to implement. If the user already explicitly chose a broader
feature, preserve that choice and explain its additional implementation and
verification cost.

Carry the user's accepted risks, supported scenarios, exclusions, and acceptance
checks through every assessment and follow-up. Do not reopen an accepted
limitation or a rejected candidate without changed facts or an explicit user
decision, and describe that basis when reopening it.

When a mechanism repeatedly needs edge-case patches, reconsider the approach
before adding another layer. Offer the simplest behavior that meets the goal,
including a narrower supported input when appropriate. Structured evidence can
validate identity or freshness; extra JSON fields cannot prove that a model's
semantic judgment is correct. Require a concrete contract failure before
proposing a new validator or state machine.

## Completion and follow-ups

A follow-up checks agreed fixes, the delta, and affected consumers and failure
paths. New regressions and consequential missed requirements remain actionable;
unrelated improvements do not automatically extend the task. When successive
fixes expand one mechanism, assess simplification against the agreed goal before
requesting another layer. A new feature needs a separate scope decision with its
cost explained.

Completion means the agreed result and acceptance checks are satisfied, required
findings are closed, and affected regressions are checked; it does not mean
proving that no possible defect exists. State residual limitations and
incomplete checks. Do not use a fixed round limit or a severity-only cutoff to
hide a real regression. Do not automatically recommend another broad review
after successful completion, or describe a targeted check as proof that all
possible defects are absent.
