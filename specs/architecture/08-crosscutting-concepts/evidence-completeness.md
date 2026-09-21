# Evidence and Completeness

Evidence is complete only when required inputs, files, dependencies, checks, and
revision bindings are observed. Partial, stale, unknown, or contradictory
evidence is never presented as complete. Semantic reviews inspect the relevant
repository sources, tests, schemas, configuration, and evals directly.
Formal specification validation proves only its enumerated structural checks.
Historical properties without an explicit baseline are `not_checked`, and a
successful result supplies no evidence about prose language, semantic quality,
architectural significance, extension boundaries, or repository drift.
