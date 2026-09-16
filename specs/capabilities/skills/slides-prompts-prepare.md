# `slides-prompts-prepare`

## Purpose

Prepare cohesive image prompts by combining a user-selected theme with factual
slide content and concise team or technology references.

## Triggers and Near-Misses

Trigger for slides or prompts; near-miss: sending a presentation or choosing a channel.

## Inputs and Outputs

Input is the fixed action, an automatically resolved default profile or explicit
context override, an existing presentation, and a selected or saved visual
direction. Output is one English prompt file per slide.

## Workflow Stages

Resolve or self-setup the profile, research named themes when needed, analyze
every slide, map theme plus factual technical references, draft one prompt per
slide, verify coverage and unchanged images, write prompts, and report.

## Dependencies

Shared team profile runtime, presentation and repository evidence, and current
web research for named external themes.

## Remote/Local Effects

Read-only research and direct bounded prompt-file writes; no presentation, image,
publication, or external-message mutation.

## Errors, Partial, Escalation

Missing profile fields trigger guided self-setup. Missing slides, unsupported
facts, uncertain theme references, or ambiguous overlay constraints remain explicit.

## Unique Constraints

Theme and technical content are complementary. Text or logos follow the saved
policy, remain factual and concise, and never duplicate the slide title.

## Requirement

### REQ-F-119 - Keep prompt preparation non-publishing

The skill shall prepare prompts without sending messages or publishing slides.

## Example

`slides-prompts-prepare` returns an English visual prompt with no embedded text.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
