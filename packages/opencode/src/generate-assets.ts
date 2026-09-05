import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { COMMAND_REGISTRY, renderCommand } from "./registry.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const commandsRoot = resolve(packageRoot, "assets", "commands");

await mkdir(commandsRoot, { recursive: true });
for (const command of COMMAND_REGISTRY) {
  await writeFile(resolve(commandsRoot, `${command.name}.md`), renderCommand(command), "utf8");
}
