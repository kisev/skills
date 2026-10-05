# Golden fixture provenance

These 33 fixtures were generated and byte-checked against the TypeScript
reviewmatic implementation at source revision
`3e409c217e94d643f77eb543caab9a2ed4b7288d`, before that implementation was
removed. At that revision, the TypeScript baseline was 195 backend tests plus 6
TUI tests (201 total, all passing). The transition outputs and TypeScript
verdicts remain the frozen expected values in the JSON fixtures.

There is no fixture generator. The Python suite recomputes digests, validation
results, and state-machine outputs and compares each result with those retained
expectations. Do not update expected values by running the Python implementation.
