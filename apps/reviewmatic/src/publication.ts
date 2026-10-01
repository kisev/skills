import { readdirSync, readFileSync } from "node:fs";
import { WorkflowError, gitRead } from "./contract.js";
import { runMutationProcess, type MutationProcessResult } from "./mutation-process.js";

type Json = Record<string, unknown>;

export function shellQuote(value: string): string {
  return /^[\w@%+=:,./-]+$/.test(value) ? value : `'${value.replace(/'/g, "'\\''")}'`;
}

export function shellJoin(argv: string[]): string {
  return argv.map(shellQuote).join(" ");
}

// Parse only the quoting emitted by shellJoin. Commands are never executed by a shell.
export function commandArgv(command: string): string[] {
  const result: string[] = [];
  let token = "",
    quote = "",
    started = false;
  for (let index = 0; index < command.length; index += 1) {
    const character = command[index];
    if (quote !== "") {
      if (character === quote) quote = "";
      else token += character;
    } else if (character === "'") {
      quote = character;
      started = true;
    } else if (character === "\\") {
      if (++index >= command.length) throw new WorkflowError("Incomplete command escape");
      token += command[index];
      started = true;
    } else if (/\s/.test(character)) {
      if (started) result.push(token);
      token = "";
      started = false;
    } else {
      token += character;
      started = true;
    }
  }
  if (quote !== "") throw new WorkflowError("Incomplete command quote");
  if (started) result.push(token);
  if (result[0] !== "glab")
    throw new WorkflowError("Legacy guarded actions are historical only; prepare a new runbook");
  return result;
}

export async function makeCommand(
  root: string,
  evidence: Json,
  _context: Json,
  _actionId: string,
  argv: string[],
  _value: Json,
  _dependencies: Record<string, string>,
  stdinSha256: string | null = null,
): Promise<string> {
  if (argv[1] !== "mr" || argv[2] !== "note") return shellJoin(argv);
  const directory = `${root}/artifacts/review_plan/bodies`;
  const { createHash } = await import("node:crypto");
  const name = readdirSync(directory).find(
    (name) =>
      name.endsWith(".md") &&
      createHash("sha256")
        .update(readFileSync(`${directory}/${name}`))
        .digest("hex") === stdinSha256,
  );
  if (name === undefined) throw new WorkflowError("Line publication body is unavailable");
  const side = argv.includes("--line") ? "new" : "old";
  const path = argv[argv.indexOf("--file") + 1];
  const changes = ((evidence.changed_files as Json).items as Json[]).filter(
    (item) => item[`${side}_path`] === path,
  );
  if (changes.length !== 1)
    throw new WorkflowError("Line publication requires one exact changed file");
  const project = evidence.project as Json;
  const refs = (evidence.object as Json).diff_refs as Json;
  const position: Json = {
    position_type: "text",
    ...refs,
    new_path: changes[0].new_path,
    old_path: changes[0].old_path,
    [`${side}_line`]: argv[argv.indexOf(side === "new" ? "--line" : "--old-line") + 1],
  };
  if (side === "new") {
    const wanted = Number(position.new_line);
    const repository = String((_context.exact_git as Json).repo_root);
    const diff = String(
      gitRead(repository, [
        "diff",
        "--unified=3",
        String(evidence.base_sha),
        String(evidence.head_sha),
        "--",
        path,
      ]),
    );
    let oldLine = 0,
      newLine = 0;
    for (const row of diff.split("\n")) {
      const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(row);
      if (hunk) {
        oldLine = Number(hunk[1]);
        newLine = Number(hunk[2]);
        continue;
      }
      if (row.startsWith(" ")) {
        if (newLine === wanted) Object.assign(position, { old_line: oldLine });
        oldLine += 1;
        newLine += 1;
      } else if (row.startsWith("+") && !row.startsWith("+++")) newLine += 1;
      else if (row.startsWith("-") && !row.startsWith("---")) oldLine += 1;
    }
  }
  return shellJoin([
    "glab",
    "api",
    "--hostname",
    String(project.hostname),
    "--method",
    "POST",
    `projects/${project.id}/merge_requests/${(evidence.target as Json).iid}/discussions`,
    "--silent",
    "-F",
    `body=@${directory}/${name}`,
    ...Object.entries(position).flatMap(([key, value]) => ["-f", `position[${key}]=${value}`]),
  ]);
}

export async function sendCommand(
  command: string,
  signal?: AbortSignal,
): Promise<MutationProcessResult> {
  return runMutationProcess(commandArgv(command), Buffer.alloc(0), { signal });
}
