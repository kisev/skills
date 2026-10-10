# Mechanical specification validation

`scripts/spec_validate.py` proves only the closed set of structural invariants
described here: Python 3.12+, standard-library-only, read-only, independent of
Git, and safe under isolated interpreter settings.

## Commands

Validate one snapshot:

```sh
python3 -I -S -B scripts/spec_validate.py check --path <specs>
```

Validate lifecycle between two supplied snapshots:

```sh
python3 -I -S -B scripts/spec_validate.py lifecycle \
  --baseline <previous-specs> \
  --candidate <current-specs>
```

`check` verifies the 19 required `README.md` files, regular UTF-8 input files,
one non-empty `Canonical language:` declaration, the `Extension Index`,
requirement and ADR identifiers, the ADR index, supported relative inline
Markdown links, and exact placeholders from the supplied templates. The
declaration proves only that a language was selected, not the language of
prose.

`lifecycle` does not infer history. It compares only the explicit baseline and
candidate, requires every baseline `REQ-*` and `ADR-*` identifier to remain,
and requires each new identifier number to exceed the baseline maximum in its
namespace. Run `check` separately per snapshot when snapshot validity is
required.

## Deterministic syntax

- The language declaration is one line beginning `Canonical language:` with a
  non-empty concrete value.
- The optional root heading is exactly `## Extension Index`. When additional
  top-level directories exist beside `requirements/` and `architecture/`, each
  has exactly one entry of the form
  `- [Name](name/README.md): Non-empty semantic boundary.`
- Requirement declarations use `### REQ-F/I/Q/C-NNN - Title`; references to an
  identifier are not declarations.
- ADR files use `NNNN-lowercase-hyphenated-title.md`; their first line uses
  `# ADR-NNNN: Title`, and the decision index links every ADR exactly once.
- Supported local Markdown links are inline links with a relative POSIX path
  and an optional fragment. URI links are not fetched. Images, reference links,
  link titles, and nested destination parentheses are outside the checked
  subset.
- Findings use paths relative to each snapshot's supplied root.

## JSON contract

Every invocation writes exactly one UTF-8 JSON document to standard output,
nothing else. Schema version `spec-validate/v1`:

```json
{
  "schema_version": "spec-validate/v1",
  "mode": "check",
  "status": "valid",
  "checks": {
    "snapshot": "passed",
    "lifecycle": "not_checked"
  },
  "findings": [],
  "errors": []
}
```

`mode` is `check`, `lifecycle`, or `help`; `status` is `valid`, `invalid`, or
`error`; each check is `passed`, `failed`, or `not_checked`. A finding contains
`code`, relative POSIX `path`, one-based `line` and `column` (`0` when no exact
location exists), and `message`; findings sort by `(code, path, line, column)`.
An input or execution error contains stable `code` and `message` and never
exposes an absolute path.

Exit status `0` means all requested invariants passed, `1` validation findings
exist, and `2` invocation, input, or execution failure. `--help` returns the
same JSON contract with exit status `0`.

## Deliberate limits

The runner does not assess semantic duplication, requirement quality or
atomicity, architectural significance, extension-boundary correctness,
repository drift, process content by meaning or keyword, or whether prose uses
the declared language. A successful result is necessary formal evidence, not a
replacement for `spec-review`.
