import type { Plugin } from "@opencode/plugin";
import { subscribeEvents } from "./events.js";
export type ZedBellOptions = { enabled?: boolean };

export async function zedBell(options: ZedBellOptions = {}) {
  if (!options.enabled) return {};
  return {
    event: async (event: { type: string }) => {
      if (event.type !== "session.idle" && event.type !== "permission.asked") return;
      const acp = process.env.OPENCODE_CLIENT === "acp" || process.argv.includes("acp");
      if (!acp) process.stdout.write("\x07");
    },
  };
}

export default {
  id: "agentomatic.zed-bell",
  async setup(ctx) {
    const hooks = await zedBell(ctx.options);
    if (hooks.event) return subscribeEvents(ctx, hooks.event);
  },
} satisfies Plugin.Plugin;
