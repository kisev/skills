import { tool } from "@opencode-ai/plugin";

import {
  bootstrapContext,
  forgetEntry,
  getEntry,
  opencodeDatabasePath,
  openMemomatic,
  searchMemory,
  sessionFacts,
  writeEntry,
  type MemomaticContext,
} from "@kisev/memomatic";

export type MemomaticOptions = {
  enabled?: boolean;
  bootstrapBudgetChars?: number;
  bootstrapEpisodicBudgetChars?: number;
};

async function withContext<T>(work: (context: MemomaticContext) => Promise<T>): Promise<string> {
  const context = await openMemomatic();
  try {
    return JSON.stringify(await work(context));
  } finally {
    context.store.close();
  }
}

export async function memomatic(options: MemomaticOptions = {}) {
  if (options.enabled === false) return {};
  const curatedBudget = options.bootstrapBudgetChars ?? 4_000;
  const episodicBudget = options.bootstrapEpisodicBudgetChars ?? 1_500;
  const memorySearch = tool({
    args: { query: tool.schema.string() },
    description:
      "Search personal long-term memory for durable decisions, discoveries, failed attempts, and session outcomes.",
    async execute(args: { query: string }) {
      return withContext((context) => searchMemory(context, args.query));
    },
  });
  const memoryGet = tool({
    args: {
      file: tool.schema.string(),
      line: tool.schema.number().optional(),
    },
    description:
      "Read a memomatic memory file fully or one line. Fetching a line marks that entry as useful.",
    async execute(args: { file: string; line?: number }) {
      return withContext((context) => getEntry(context, args.file, args.line));
    },
  });
  const memoryWrite = tool({
    args: {
      text: tool.schema.string(),
      target: tool.schema.enum(["episodic", "curated", "user"]).optional(),
      origin: tool.schema.enum(["user", "agent"]).optional(),
      key: tool.schema.string().optional(),
      project: tool.schema.string().optional(),
      source: tool.schema.string().optional(),
      importance: tool.schema.number().min(1).max(10).optional(),
      trigger: tool.schema.array(tool.schema.string()).optional(),
      pinned: tool.schema.boolean().optional(),
    },
    description:
      "Queue a durable memory entry for the next process/dream pass: standing decisions with rationale, discoveries, failed attempts with rejection reasons, session outcomes, action-sensitive boundaries. Pass source=<skill-name> when a skill workflow requests the save. Respect MEMORY_RULES.md; never-save topics are rejected.",
    async execute(args: {
      text: string;
      target?: "episodic" | "curated" | "user";
      origin?: "user" | "agent";
      key?: string;
      project?: string;
      source?: string;
      importance?: number;
      trigger?: string[];
      pinned?: boolean;
    }) {
      return withContext((context) =>
        writeEntry(context, {
          importance: args.importance,
          key: args.key,
          origin: args.origin,
          pinned: args.pinned,
          project: args.project,
          source: args.source,
          target: args.target,
          text: args.text,
          trigger: args.trigger,
        }),
      );
    },
  });
  const memoryForget = tool({
    args: { file: tool.schema.string(), line: tool.schema.number() },
    description: "Remove one entry line from a memomatic memory file (explicit deletion only).",
    async execute(args: { file: string; line: number }) {
      return withContext((context) => forgetEntry(context, args));
    },
  });
  return {
    "experimental.chat.system.transform": async (
      input: { sessionID?: string },
      output: { system: string[] },
    ) => {
      try {
        const context = await openMemomatic();
        try {
          const facts = input.sessionID
            ? sessionFacts(opencodeDatabasePath(), input.sessionID)
            : { directory: null, title: null, firstMessage: null };
          const block = await bootstrapContext(context, facts, {
            curatedBudgetChars: curatedBudget,
            episodicBudgetChars: episodicBudget,
          });
          if (block) output.system.push(block);
        } finally {
          context.store.close();
        }
      } catch {
        // Memory bootstrap must never break the session.
      }
    },
    tool: {
      memory_forget: memoryForget,
      memory_get: memoryGet,
      memory_search: memorySearch,
      memory_write: memoryWrite,
    },
  };
}

export default memomatic;
