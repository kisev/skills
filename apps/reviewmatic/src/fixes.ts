import { gitRead, isDict, nonemptyString, WorkflowError } from "./contract.js";

type Json = Record<string, unknown>;
export type SuggestionPart = { path: string; line: number; body: string };

// A part with its own explanation is a complete publication body. Bare legacy
// blocks retain the shared explanation so old guided drafts remain readable.
export function suggestionBody(shared: string, part: SuggestionPart): string {
  const prose = part.body
    .replace(/^```suggestion(?::-\d+\+\d+)?\n[\s\S]*?\n```[ \t]*(?:\n|$)/gm, "")
    .trim();
  return prose ? part.body : `${shared}\n\n${part.body}`;
}

export function suggestionParts(fix: Json): SuggestionPart[] {
  if (fix.suggestions !== undefined) {
    if (
      !Array.isArray(fix.suggestions) ||
      fix.suggestions.length === 0 ||
      fix.suggestions.length > 50 ||
      !fix.suggestions.every(
        (part) =>
          isDict(part) &&
          Object.keys(part).sort().join(",") === "body,line,path" &&
          nonemptyString(part.path) &&
          Number.isInteger(part.line) &&
          Number(part.line) > 0 &&
          nonemptyString(part.body),
      )
    )
      throw new WorkflowError("suggestions requires bounded path/line/body records");
    if (fix.suggestions.length > 1 && !nonemptyString(fix.split_rationale))
      throw new WorkflowError(
        "Related suggestions require split_rationale explaining safe partial application",
      );
    return fix.suggestions as SuggestionPart[];
  }
  return [{ path: String(fix.path), line: Number(fix.line), body: String(fix.body) }];
}

export function suggestionRange(body: string): {
  before: number;
  after: number;
  replacement: string[];
} {
  const matches = [
    ...body.matchAll(/^```suggestion(?::-([0-9]+)\+([0-9]+))?\n([\s\S]*?)\n```[ \t]*(?:\n|$)/gm),
  ];
  if (matches.length !== 1)
    throw new WorkflowError("Each suggestion part requires exactly one suggestion block");
  const match = matches[0];
  const before = Number(match[1] ?? 0),
    after = Number(match[2] ?? 0);
  if (before > 100 || after > 100)
    throw new WorkflowError("Suggestion range exceeds the supported limit");
  return { before, after, replacement: match[3] === "" ? [] : match[3].split("\n") };
}

// Build the complete result against one revision, not a sequence of drifting line numbers.
export function suggestionsPatch(
  repoRoot: string,
  headSha: string,
  parts: SuggestionPart[],
): string {
  const groups = new Map<string, SuggestionPart[]>();
  for (const part of parts) {
    if (part.path.startsWith("/") || part.path.split("/").includes(".."))
      throw new WorkflowError("Suggestion path escapes the repository");
    groups.set(part.path, [...(groups.get(part.path) ?? []), part]);
  }
  let patch = "";
  for (const [path, values] of groups) {
    const entry = String(gitRead(repoRoot, ["ls-tree", headSha, "--", path]));
    if (!/^100(?:644|755) blob /.test(entry))
      throw new WorkflowError("Suggestion requires a regular existing file");
    const source = String(gitRead(repoRoot, ["show", `${headSha}:${path}`]));
    const trailingNewline = source.endsWith("\n");
    const original = (trailingNewline ? source.slice(0, -1) : source).split("\n");
    const edits = values
      .map((part) => ({ ...part, ...suggestionRange(part.body) }))
      .sort((a, b) => a.line - a.before - (b.line - b.before));
    let end = 0;
    for (const edit of edits) {
      const start = edit.line - edit.before;
      if (start < 1 || edit.line + edit.after > original.length || start <= end)
        throw new WorkflowError("Related suggestion ranges overlap or escape the reviewed file");
      end = edit.line + edit.after;
    }
    const updated = [...original];
    for (const edit of edits.reverse())
      updated.splice(
        edit.line - edit.before - 1,
        edit.before + edit.after + 1,
        ...edit.replacement,
      );
    if (updated.join("\n") === original.join("\n"))
      throw new WorkflowError("Suggestion does not change the reviewed file");
    patch +=
      `diff --git ${JSON.stringify(`a/${path}`)} ${JSON.stringify(`b/${path}`)}\n` +
      `--- ${JSON.stringify(`a/${path}`)}\n+++ ${JSON.stringify(`b/${path}`)}\n` +
      `@@ -1,${original.length} +${updated.length === 0 ? 0 : 1},${updated.length} @@\n` +
      original
        .map(
          (line, index) =>
            `-${line}\n${!trailingNewline && index === original.length - 1 ? "\\ No newline at end of file\n" : ""}`,
        )
        .join("") +
      updated
        .map(
          (line, index) =>
            `+${line}\n${!trailingNewline && index === updated.length - 1 ? "\\ No newline at end of file\n" : ""}`,
        )
        .join("");
  }
  return patch;
}
