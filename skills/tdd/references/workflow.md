# tdd Workflow

Test-first development with a human in the loop. The loop produces tests worth
keeping: they verify behavior through public interfaces, not implementation
details, so they survive refactors that do not change behavior.

## Scope

Apply when building a feature or fixing a bug test-first. Do not apply to
exploration without acceptance criteria, mechanical refactors covered by
existing tests, or documentation-only changes. Debugging a failing behavior
belongs to `debugging`; this skill owns the green path after a fix is agreed.

## Seams come first, with the user

A **seam** is the public boundary where a test observes behavior without
reaching inside the implementation. Before writing any test:

1. Name the seams under test: the public interfaces whose behavior this work
   must specify.
2. Confirm the seam list with the user before writing tests. Seams are agreed,
   not discovered silently mid-loop.
3. Write no test at an unconfirmed seam. If a new seam turns out to be needed,
   propose it and get confirmation before testing there.

This is deliberate human-in-the-loop control: agreeing seams up front lands
testing effort on critical paths and complex logic instead of every edge case.

## The loop: vertical slices

Work in vertical slices — one test, one minimal implementation, repeat. Each
slice is a tracer bullet that responds to what the previous cycle taught.

- **Red before green.** Write the failing test first, run it, watch it fail
  for the expected reason, then write only enough implementation to pass it.
- **One slice at a time.** One seam, one test, one minimal implementation per
  cycle. Do not anticipate future tests or add speculative generality.
- **Refactor is not part of the loop.** Behavior-preserving cleanup after the
  cycle belongs to the review stage; keep the loop red-green only.

A larger feature is a sequence of slices: specify the first behavior, make it
pass, learn, then choose the next behavior the user cares about — never a bulk
of tests written against imagined code.

## Anti-patterns

- **Tautological tests.** The assertion recomputes the expectation the same way
  the code does, so it passes by construction and can never disagree. Expected
  values come from an independent source of truth: a known-good literal, a
  worked example, or the specification.
- **Horizontal slicing.** Writing all tests first, then all implementation.
  Bulk tests verify imagined behavior and commit to test structure before the
  implementation is understood. Slice vertically instead.
- **Implementation-coupled tests.** Mocking internal collaborators, testing
  private methods, or verifying through a side channel such as querying the
  database instead of using the interface. The tell: the test breaks when you
  refactor although behavior has not changed.
- **Unagreed seams.** Any test written before the seam list is confirmed with
  the user. Delete or move it to an agreed seam.

## Completion

The work is done when every agreed seam has at least one test that failed
first and now passes, no test encodes implementation details, and the full
suite is green. Report which seams are covered and which known behaviors
remain untested. Completion claims still require fresh verification evidence;
inside a repository, its own verification contracts take precedence over this
summary.

## Credits

Inspired by `mattpocock/skills` (`engineering/tdd`), MIT, Copyright (c) 2026
Matt Pocock; the pinned revision is recorded in the frontmatter
`metadata.inspired-by` field. This workflow is an original adaptation of those
ideas for this collection, not a copy of the upstream text.
