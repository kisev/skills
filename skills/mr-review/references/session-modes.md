# Startup Round and Profiles

## One round

The startup round asks, once, immediately after collection:

- the OCR reviewer aliases and effort — default the profile default and
  `medium`;
- the task baseline — goal, acceptance criteria, constraints, open questions.

There is no clean-versus-incremental question and no second round. Everything
after the answer runs autonomously until the chat report.

## Profiles

The global profile is `~/.reviewmatic/reviewers.json`. The local profile is
`./.reviewmatic/reviewers.json`, searched in the current directory and then the
git root; the first local file overlays the global one.

- A matching alias replaces the global entry.
- A new alias adds to the set.
- The local `default` wins over the global `default`.

Read the effective profile with:

```shell
reviewmatic profiles
```

The printed result names the sources, the default, every reviewer, and the
provider validation. The validation checks provider names with
`ocr llm providers`: a provider outside the built-in list is reported as
unknown, because custom providers are configured only in OCR's own
configuration. Do not treat an unknown provider as a rejection; do not read
`~/.opencodereview/config.json`.

## Contents

```json
{
  "default": "fast",
  "reviewers": [
    {"alias": "fast", "provider": "openai", "model": "gpt-5", "effort": "medium"},
    {"alias": "deep", "provider": "anthropic", "model": "claude-opus-5", "effort": "high"}
  ]
}
```

Only `alias`, `provider`, `model`, and `effort` are allowed. The profile never
holds secrets; a credential-looking key is rejected. When the human saves a
one-off choice, write only those four fields.

## Without a profile

When neither file exists, use OCR's configured default or ask for a one-off
provider and model and offer to save them as an alias. Several selected aliases
run as parallel OCR processes; the manager merges the results.
