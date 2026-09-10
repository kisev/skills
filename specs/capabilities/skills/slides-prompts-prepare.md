# `slides-prompts-prepare`

## Purpose

Prepare structured slide and illustration prompts from a bounded team context.

## Triggers and Near-Misses

Trigger for slides or prompts; near-miss: sending a presentation or choosing a channel.

## Inputs and Outputs

Input is explicit context and audience. Output is English prompt material and plan.

## Workflow Stages

Resolve context, collect evidence, draft prompts, check constraints, report.

## Dependencies

Team context and repository evidence.

## Remote/Local Effects

Local reads and plan artifact; no publication or external message.

## Errors, Partial, Escalation

Missing context is partial; sensitive material is escalated.

## Unique Constraints

Illustration prompts contain no text or logos unless explicitly allowed by contract.

## Requirement

### REQ-F-119 - Keep prompt preparation non-publishing

The skill shall prepare prompts without sending messages or publishing slides.

## Example

`slides-prompts-prepare` returns an English visual prompt with no embedded text.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
