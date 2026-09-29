import type { Plugin } from "@opencode/plugin";
import { registerV2Hooks } from "./compatibility.js";
export type ZedBellOptions = { enabled?: boolean };

export async function zedBell(options: ZedBellOptions = {}) {
  if (!options.enabled) return {};
  return {
    event: async ({ event }: { event: { type?: string } }) => {
      if (event.type !== "session.idle" && event.type !== "permission.asked") return;
      const acp = process.env.OPENCODE_CLIENT === "acp" || process.argv.includes("acp");
      if (!acp) process.stdout.write("\x07");
    },
  };
}

export default {
  id: "agentomatic.zed-bell",
  server: async (_input: unknown, options: ZedBellOptions = {}) => zedBell(options),
  async setup(ctx) {
    return registerV2Hooks(ctx, await zedBell(ctx.options));
  },
} satisfies Plugin.Plugin & { server: unknown };
