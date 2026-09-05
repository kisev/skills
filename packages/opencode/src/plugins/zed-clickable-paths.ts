export type ZedClickablePathsOptions = { enabled?: boolean };

const INSTRUCTION = "Whenever you reference a local filesystem file in user-facing chat prose, format it as a Markdown link: [filename](file:///absolute/percent-encoded/path). Use a short filename as the label and an absolute percent-encoded file:// URI as the target. Do not create these links inside code, commands, patches, logs, quoted text, URLs, artifacts, or structured output.";

export async function zedClickablePaths(options: ZedClickablePathsOptions = {}) {
  if (!options.enabled) return {};
  return { "experimental.chat.system.transform": async (_input: unknown, output: { system?: unknown[] }) => {
    if (Array.isArray(output.system) && !output.system.includes(INSTRUCTION)) output.system.push(INSTRUCTION);
  } };
}

export default zedClickablePaths;
