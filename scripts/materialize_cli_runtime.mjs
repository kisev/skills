import { readFile, mkdir, writeFile, rename } from "node:fs/promises";
import { resolve, dirname } from "node:path";
const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(
  await readFile(resolve(root, "shared/manifest.json"), "utf8"),
).npmRuntime;
const source = await readFile(resolve(root, "shared", manifest.source), "utf8");
for (const destination of manifest.destinations) {
  const path = resolve(root, destination);
  if (!path.startsWith(`${root}/`) || !destination.endsWith("/src/generated/cli.ts"))
    throw new Error("invalid CLI runtime destination");
  if (process.argv.includes("--check")) {
    if ((await readFile(path, "utf8")) !== source)
      throw new Error(`shared CLI runtime drift: ${destination}`);
    continue;
  }
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  await writeFile(temporary, source);
  await rename(temporary, path);
}
