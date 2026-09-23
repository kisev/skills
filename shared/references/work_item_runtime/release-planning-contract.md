# Task Release Planning Contract

Every GitLab task planning decision has four exact sections: `decision`,
`semver`, `release`, and `milestone`. The shared validator checks their closed
vocabularies, rationale, confidence, release compatibility, and milestone catalog
binding. It does not infer project release policy.

`decision.status` is `accepted`, `deferred`, `rejected`, `duplicate`, or
`obsolete`. Only a semantically `ready` task may be accepted. `semver.level` is
`major`, `minor`, `patch`, `none`, `not_applicable`, or `unknown`; accepted work
cannot remain `unknown`, and `none` or `not_applicable` requires at least a patch
release. `release` names the established policy, published baseline, exact target
version, target release impact, rationale, and confidence.

`milestone.status` is `selected`, `create`, `none`, `remove`, or `unknown`.
Selected milestones require an exact active catalog ID. Proposed milestones bind
the project, title, and normalized version but have a null ID until they are
created and recollected. Non-accepted work has no milestone; an existing
assignment requires `remove`.

The planning verdict is `ready`, `needs_clarification`, or `blocked`. A proposed
milestone needs clarification. A closed or SemVer-incompatible milestone blocks.
Dates do not determine compatibility. Each project or independently versioned
component is assessed on its own release line.

Use this exact shape:

```json
{
  "decision": {
    "status": "accepted",
    "rationale": "The task is current, distinct, and semantically ready.",
    "confidence": "high"
  },
  "semver": {
    "level": "patch",
    "rationale": "The task corrects existing public behavior.",
    "confidence": "high"
  },
  "release": {
    "policy": "Published stable tags define this component release line.",
    "baseline_version": "1.4.0",
    "target_version": "1.5.0",
    "impact": "minor",
    "rationale": "The next planned release already contains compatible features.",
    "confidence": "high"
  },
  "milestone": {
    "status": "selected",
    "candidate": {
      "project_id": 19,
      "id": 27,
      "title": "v1.5.0",
      "state": "active",
      "version": "1.5.0"
    },
    "rationale": "This is the nearest compatible active release milestone.",
    "confidence": "high"
  }
}
```

The catalog input for `scripts/release_plan.py` is
`{"milestones":[...]}` using observed GitLab milestone objects extended with
their numeric `project_id`. Pass the semantic quality verdict separately. An
existing assignment is passed as `--current-milestone-id`.
