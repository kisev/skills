import { mkdir, readFile, readdir, unlink, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { COMMAND_REGISTRY, renderCommand } from "./registry.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const arguments_ = process.argv.slice(2);
const rootIndex = arguments_.indexOf("--root");
if (rootIndex !== -1 && !arguments_[rootIndex + 1]) throw new Error("--root requires a path");
const commandsRoot =
  rootIndex === -1
    ? resolve(packageRoot, "assets", "commands")
    : resolve(arguments_[rootIndex + 1] ?? "");
const check = arguments_.includes("--check");
const expectedNames = new Set(COMMAND_REGISTRY.map((command) => `${command.name}.md`));

if (!check) await mkdir(commandsRoot, { recursive: true });
const entries = await readdir(commandsRoot, { withFileTypes: true }).catch(() => []);
for (const entry of entries) {
  if (entry.isFile() && !expectedNames.has(entry.name)) {
    if (check) throw new Error(`unexpected generated asset: ${entry.name}`);
    await unlink(resolve(commandsRoot, entry.name));
  } else if (!entry.isFile()) {
    throw new Error(`unexpected entry in generated assets: ${entry.name}`);
  }
}
for (const command of COMMAND_REGISTRY) {
  const destination = resolve(commandsRoot, `${command.name}.md`);
  const expected = renderCommand(command);
  if (check) {
    const actual = await readFile(destination, "utf8").catch(() => "");
    if (actual !== expected) throw new Error(`generated asset drift: ${command.name}.md`);
  } else {
    await writeFile(destination, expected, "utf8");
  }
}
