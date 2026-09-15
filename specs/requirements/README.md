# Requirements

This section contains the normative English contracts for the current target.
Requirements are atomic, observable, uniquely identified, and traceable to
evidence. The machine-readable public-surface and compatibility contracts remain
the syntax source of truth.

- [Functional](functional/README.md): behavior of public capabilities and lifecycle.
- [Interfaces](interfaces/README.md): skills, commands, package tools, and host boundaries.
- [Quality](quality/README.md): measurable safety, completeness, reproducibility, and compatibility.
- [Constraints](constraints/README.md): ownership, distribution, mutation, and scope limits.

IDs use `REQ-F-NNN`, `REQ-I-NNN`, `REQ-Q-NNN`, and `REQ-C-NNN`. A requirement
block is hashed in `traceability.json`; requirement text is not duplicated there.
Each namespace is append-only: new numbers exceed its historical maximum, and a
retired ID remains as a compact record of the former requirement and its outcome.
