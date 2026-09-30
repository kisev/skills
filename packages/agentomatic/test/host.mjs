import core from "../dist/index.js";

export function host(
  directory = "/project",
  options = {},
  agents = [
    {
      id: "mapper",
      permissions: [
        { action: "*", resource: "*", effect: "allow" },
        { action: "edit", resource: "*", effect: "deny" },
      ],
    },
  ],
) {
  const hooks = {};
  const tools = new Map();
  let emit;
  let aborted = false;
  const context = {
    location: { directory },
    options,
    agent: { list: async () => ({ data: agents }) },
    tool: {
      hook: async (name, callback) => {
        hooks[name] = callback;
      },
      transform: async (callback) => callback({ add: (tool) => tools.set(tool.name, tool) }),
    },
    session: {
      hook: async (name, callback) => {
        hooks[name] = callback;
      },
      get: async () => ({ location: { directory } }),
    },
    event: {
      subscribe: async function* ({ signal }) {
        signal.addEventListener(
          "abort",
          () => {
            aborted = true;
            emit?.();
          },
          { once: true },
        );
        while (!signal.aborted) {
          const event = await new Promise((resolve) => {
            emit = resolve;
          });
          if (event) yield event;
        }
      },
    },
  };
  return { context, hooks, tools, emit: (event) => emit(event), aborted: () => aborted };
}

export async function setupCore(agents) {
  const state = host("/project", {}, agents);
  await core.setup(state.context);
  return {
    ...state,
    route: async (args, context) => {
      const tool = state.tools.get("route");
      return (await tool.execute(tool.input.parse(args), context)).content;
    },
  };
}
