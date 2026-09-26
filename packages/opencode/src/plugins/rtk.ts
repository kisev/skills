import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

import { stateRoot, withStateLock } from "../runtime/state.js";
import { writeAtomic } from "../lifecycle.js";

const THRESHOLD = 8_000;
const FILTERS: ReadonlyArray<{ prefix: readonly string[]; filter: string }> = [
  { prefix: ["git", "log"], filter: "git-log" },
  { prefix: ["git", "diff"], filter: "git-diff" },
  { prefix: ["git", "status"], filter: "git-status" },
  { prefix: ["rg"], filter: "grep" },
  { prefix: ["grep"], filter: "grep" },
  { prefix: ["pytest"], filter: "pytest" },
  { prefix: ["tsc"], filter: "tsc" },
];
const RECENT_EVENTS_CAP = 20;
const CHARS_PER_TOKEN = 4;
type HookInput = { tool: string; args?: { command?: unknown } };
type HookOutput = { output?: unknown };
export type RtkMethod =
  | "compressed-rtk"
  | "truncated-head-tail"
  | "rtk-unavailable"
  | "ineligible"
  | "below-threshold";
export type RtkStats = {
  schema_version: 1;
  counters: Record<RtkMethod, number>;
  chars_original: number;
  chars_final: number;
  recent: Array<{ at: string; method: RtkMethod; original: number; final: number }>;
  updated_at: string;
};
export type RtkOptions = {
  enabled?: boolean;
  bin?: string;
  threshold?: number;
  run?: (filter: string, input: string) => Promise<string | undefined>;
  statsPath?: string | null;
};

export function emptyRtkStats(): RtkStats {
  return {
    schema_version: 1,
    counters: {
      "compressed-rtk": 0,
      "truncated-head-tail": 0,
      "rtk-unavailable": 0,
      ineligible: 0,
      "below-threshold": 0,
    },
    chars_original: 0,
    chars_final: 0,
    recent: [],
    updated_at: "",
  };
}

export function rtkStatsPath(home = homedir()): string {
  return join(stateRoot("rtk", home), "stats.json");
}

export function rtkCharsSaved(stats: RtkStats): number {
  return Math.max(0, stats.chars_original - stats.chars_final);
}

export function rtkTokensSavedEstimate(stats: RtkStats): number {
  return Math.ceil(rtkCharsSaved(stats) / CHARS_PER_TOKEN);
}

export async function readRtkStats(path = rtkStatsPath()): Promise<RtkStats | undefined> {
  let raw: string;
  try {
    raw = await readFile(path, "utf8");
  } catch {
    return undefined;
  }
  try {
    const value = JSON.parse(raw) as Partial<RtkStats>;
    if (
      value.schema_version !== 1 ||
      !value.counters ||
      typeof value.counters !== "object" ||
      Array.isArray(value.counters)
    )
      return undefined;
    const base = emptyRtkStats();
    for (const method of Object.keys(base.counters) as RtkMethod[]) {
      const counter = value.counters[method];
      if (Number.isSafeInteger(counter) && counter >= 0) base.counters[method] = counter;
    }
    return {
      ...base,
      chars_original: Number.isSafeInteger(value.chars_original) ? value.chars_original! : 0,
      chars_final: Number.isSafeInteger(value.chars_final) ? value.chars_final! : 0,
      recent: Array.isArray(value.recent)
        ? value.recent.filter(
            (item): item is RtkStats["recent"][number] =>
              Boolean(item) &&
              typeof item === "object" &&
              typeof item.at === "string" &&
              typeof item.method === "string" &&
              item.method in base.counters &&
              typeof item.original === "number" &&
              typeof item.final === "number",
          )
        : [],
      updated_at: typeof value.updated_at === "string" ? value.updated_at : "",
    };
  } catch {
    return undefined;
  }
}

async function recordStats(path: string, method: RtkMethod, original: number, final: number) {
  const boundary = dirname(path);
  await withStateLock(boundary, async () => {
    const current = (await readRtkStats(path)) ?? emptyRtkStats();
    current.counters[method] += 1;
    if (method !== "below-threshold") {
      current.chars_original += original;
      current.chars_final += final;
    }
    current.recent = [
      ...current.recent.filter((item) => item.at !== ""),
      { at: new Date().toISOString(), method, original, final },
    ].slice(-RECENT_EVENTS_CAP);
    current.updated_at = new Date().toISOString();
    await writeAtomic(path, Buffer.from(`${JSON.stringify(current)}\n`), 0o600);
  });
}

function filter(command: string): string | undefined {
  if (/[|;$&\n()`]/.test(command)) return undefined;
  if (/\b(--json|--format(?:=|\s)|diagnos|security|deploy|migrat|delete|remove)\b/i.test(command))
    return undefined;
  const values = command.trim().split(/\s+/);
  return FILTERS.find((item) => item.prefix.every((part, index) => values[index] === part))?.filter;
}
function truncate(value: string): string {
  const points = Array.from(value);
  const size = 3_200;
  return points.length <= size * 2
    ? value
    : `${points.slice(0, size).join("")}\n…\n${points.slice(-size).join("")}`;
}
function external(binary: string, selected: string, input: string): Promise<string | undefined> {
  return new Promise((done) => {
    const child = spawn(binary, ["pipe", "--filter", selected], {
      stdio: ["pipe", "pipe", "ignore"],
      timeout: 5_000,
    });
    let output = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      output += chunk;
    });
    child.once("error", () => done(undefined));
    child.once("close", (code) => done(code === 0 ? output : undefined));
    child.stdin.end(input, "utf8");
  });
}

export async function rtk(options: RtkOptions = {}) {
  if (options.enabled === false) return {};
  const run =
    options.run ??
    ((selected: string, input: string) => external(options.bin ?? "rtk", selected, input));
  const statsPath = options.statsPath === null ? undefined : (options.statsPath ?? rtkStatsPath());
  return {
    "tool.execute.after": async (input: HookInput, output: HookOutput) => {
      try {
        if (
          input.tool === "edit" &&
          typeof output.output === "string" &&
          /oldString (not found|found multiple times|and newString must be different)/i.test(
            output.output,
          )
        )
          output.output = `${output.output}\nSTOP. Read the file before retrying Edit.`;
        if (
          input.tool !== "bash" ||
          typeof output.output !== "string" ||
          output.output.length < (options.threshold ?? THRESHOLD)
        ) {
          if (input.tool === "bash" && typeof output.output === "string" && statsPath)
            await recordStats(
              statsPath,
              "below-threshold",
              output.output.length,
              output.output.length,
            );
          return;
        }
        const selected =
          typeof input.args?.command === "string" ? filter(input.args.command) : undefined;
        const compressed = selected ? await run(selected, output.output) : undefined;
        const result =
          compressed && compressed.length < output.output.length
            ? compressed
            : truncate(output.output);
        const originalSize = output.output.length;
        output.output = `${result}\n[rtk: compressed method=${result === compressed ? `rtk/${selected}` : "head+tail"}; sizes=${originalSize}->${result.length}; evidence_complete=false; loss=possible]`;
        if (statsPath) {
          const method: RtkMethod =
            result === compressed
              ? "compressed-rtk"
              : selected === undefined
                ? "ineligible"
                : compressed === undefined
                  ? "rtk-unavailable"
                  : "truncated-head-tail";
          await recordStats(statsPath, method, originalSize, result.length);
        }
      } catch {
        /* RTK is fail-open: preserve original tool output on plugin failure. */
      }
    },
  };
}

export default rtk;
