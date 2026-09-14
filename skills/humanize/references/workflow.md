# Natural prose

## Workflow

1. Determine the audience, the author's factual role, and the text's purpose.
2. Use the language of the latest user request for all prose, defaulting to English when ambiguous, and preserve the project and ongoing conversation style unless they conflict with an explicit request. The workflow applies equally to any human language.
3. Write or edit the text according to the rules below.
4. Reread the complete result: remove repetition, unnecessary structure, and unnatural phrasing.
5. Check every generated file and the final response before saving or publishing.

## Rules

- Write directly and naturally, without bureaucratic language, advertising tone, or templated introductions.
- Use the ordinary hyphen `-` and straight double quotes `"` in newly written prose.
- Do not restate the conclusion in other words at the end or split a simple thought into unnecessary headings or lists.
- Do not confuse brevity with indifference. Keep a brief acknowledgement such as "thanks," "agreed," or "fixed" when it naturally continues the conversation.
- When the task requires reading a conversation or drafting a reply in an existing thread, use the full conversation as context. Answer an addressed question or react to a suggestion or objection first, then add only a new check or correction instead of repeating the original comment.
- In that conversation context, write from the user's factual role as shown by the available messages or MR data. Do not replace the author's role with the reviewer's role, infer their role from the current branch, or attribute actions, decisions, or promises to them.
- Name the problem, location, and consequence immediately. Preserve a path, line, variable, and technical names where the text cannot be verified without them.
- Use plain, precise language while retaining the project's familiar technical language. Do not add artificial jargon.
- Do not change exact quotations, code, commands, command output, paths, IDs, logs, APIs, file names, or external names solely for style.

## Reviews and comments

- One comment normally fits in two or three sentences.
- In a GitLab MR context, retain "thread"; do not rename exact API fields or commands.
- On a fix or objection, react briefly first, then state the necessary technical detail. Do not promise future actions on behalf of the other party.
- If a comment no longer needs action, finish it briefly: "Closing."

Before saving or publishing, reread new text aloud. If it sounds like a formal ticket-system reply, rewrite it as a short message to a colleague.

## Verification

Check generated files for punctuation that is disallowed in newly written prose:

```shell
rg -n -P '[\x{2013}\x{2014}\x{00AB}\x{00BB}]' <generated-files>
```

Keep matches that belong to exact quotations or source data. In newly written prose, fix the punctuation and reread the complete sentence instead of applying a blind replacement.
