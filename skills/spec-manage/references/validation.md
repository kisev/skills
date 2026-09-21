# Mechanical specification validation

`scripts/spec_validate.py` proves only the closed set of structural invariants
described here. It is Python 3.12+, standard-library-only, read-only, independent
of Git, and safe to run with isolated interpreter settings.

## Commands

Validate one snapshot:

```sh
python3 -I -S -B scripts/spec_validate.py check --path <specs>
```

Validate lifecycle preservation between two explicitly supplied snapshots:

```sh
python3 -I -S -B scripts/spec_validate.py lifecycle \
  --baseline <previous-specs> \
  --candidate <current-specs>
```

`check` verifies the 19 required `README.md` files, regular UTF-8 input files,
one non-empty `Canonical language:` declaration, the `Extension Index`,
requirement and ADR identifiers, the ADR index, supported relative inline
Markdown links, and exact placeholders from the supplied templates. The
declaration proves only that a language was selected; the runner does not detect
the language of prose.

`lifecycle` does not infer history. It compares only the explicit baseline and
candidate, requires every baseline `REQ-*` and `ADR-*` identifier to remain, and
requires each new identifier number to exceed the baseline maximum in its
namespace. Run `check` separately for each snapshot when snapshot validity is
required.

## Deterministic syntax

- The language declaration is one line beginning `Canonical language:` with a
  non-empty concrete value.
- The optional root heading is exactly `## Extension Index`. When additional
  top-level directories exist beside `requirements/` and `architecture/`, each
  has exactly one entry of the form
  `- [Name](name/README.md): Non-empty semantic boundary.`
- Requirement declarations use `### REQ-F/I/Q/C-NNN - Title`. References to an
  identifier are not declarations.
- ADR files use `NNNN-lowercase-hyphenated-title.md`; their first line uses
  `# ADR-NNNN: Title`. The decision index links every ADR exactly once.
- Supported local Markdown links are inline links with a relative POSIX path and
  an optional fragment. URI links are not fetched. Images, reference links, link
  titles, and nested destination parentheses are outside the checked subset.
- Findings use paths relative to the root supplied for their snapshot.

## JSON contract

Every invocation writes exactly one UTF-8 JSON document to standard output and
nothing else. Schema version `spec-validate/v1` has these fields:

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

`mode` is `check`, `lifecycle`, or `help`. `status` is `valid`, `invalid`, or
`error`. Each check is `passed`, `failed`, or `not_checked`. A finding contains
`code`, relative POSIX `path`, one-based `line` and `column` (`0` when no exact
location exists), and `message`. Findings are sorted by
`(code, path, line, column)`. An input or execution error contains stable `code`
and `message`; it never exposes an absolute path.

Exit status `0` means all requested invariants passed, `1` means validation
findings exist, and `2` means invocation, input, or execution failed. `--help`
returns the same JSON contract and exit status `0`.

## Deliberate limits

The runner does not assess semantic duplication, requirement quality or
atomicity, architectural significance, extension-boundary correctness,
repository drift, process content by meaning or keyword, or whether prose uses
the declared language. A successful result is necessary formal evidence, not a
replacement for `spec-audit`.
