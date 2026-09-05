import { spawn } from "node:child_process";

const THRESHOLD = 8_000;
const FILTERS: ReadonlyArray<{ prefix: readonly string[]; filter: string }> = [
  { prefix: ["git", "log"], filter: "git-log" }, { prefix: ["git", "diff"], filter: "git-diff" },
  { prefix: ["git", "status"], filter: "git-status" }, { prefix: ["rg"], filter: "grep" },
  { prefix: ["grep"], filter: "grep" }, { prefix: ["pytest"], filter: "pytest" }, { prefix: ["tsc"], filter: "tsc" },
];
type HookInput = { tool: string; args?: { command?: unknown } };
type HookOutput = { output?: unknown };
export type RtkOptions = { enabled?: boolean; bin?: string; threshold?: number; run?: (filter: string, input: string) => Promise<string | undefined> };

function filter(command: string): string | undefined {
  if (/[|;$&\n()`]/.test(command)) return undefined;
  const values = command.trim().split(/\s+/);
  return FILTERS.find((item) => item.prefix.every((part, index) => values[index] === part))?.filter;
}
function truncate(value: string): string {
  const points = Array.from(value); const size = 3_200;
  return points.length <= size * 2 ? value : `${points.slice(0, size).join("")}\n…\n${points.slice(-size).join("")}`;
}
function external(binary: string, selected: string, input: string): Promise<string | undefined> {
  return new Promise((done) => {
    const child = spawn(binary, ["pipe", "--filter", selected], { stdio: ["pipe", "pipe", "ignore"], timeout: 5_000 });
    let output = "";
    child.stdout.setEncoding("utf8"); child.stdout.on("data", (chunk: string) => { output += chunk; });
    child.once("error", () => done(undefined)); child.once("close", (code) => done(code === 0 ? output : undefined));
    child.stdin.end(input, "utf8");
  });
}

export async function rtk(options: RtkOptions = {}) {
  if (options.enabled === false) return {};
  const run = options.run ?? ((selected: string, input: string) => external(options.bin ?? "rtk", selected, input));
  return { "tool.execute.after": async (input: HookInput, output: HookOutput) => {
    try {
      if (input.tool === "edit" && typeof output.output === "string" && /oldString (not found|found multiple times|and newString must be different)/i.test(output.output)) output.output = `${output.output}\nSTOP. Read the file before retrying Edit.`;
      if (input.tool !== "bash" || typeof output.output !== "string" || output.output.length < (options.threshold ?? THRESHOLD)) return;
      const selected = typeof input.args?.command === "string" ? filter(input.args.command) : undefined;
      const compressed = selected ? await run(selected, output.output) : undefined;
      const result = compressed && compressed.length < output.output.length ? compressed : truncate(output.output);
      output.output = `${result}\n[rtk: compressed ${output.output.length} chars using ${compressed ? `rtk/${selected}` : "head+tail"}]`;
    } catch { /* RTK is fail-open: preserve original tool output on plugin failure. */ }
  } };
}

export default rtk;
