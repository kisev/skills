import { readFile, mkdir, writeFile, rename, readdir } from "node:fs/promises";
import { resolve, dirname, join } from "node:path";
const root = resolve(import.meta.dirname, "..");
const shared = JSON.parse(await readFile(resolve(root, "shared/manifest.json"), "utf8"));
const manifest = shared.npmRuntime;
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

// Multi-source materialization: one canonical runtime package assembled from
// several shared references. Every materialized copy is byte-identical to its
// source; the destination tree must contain exactly the declared entries.
const pythonRuntime = shared.pythonRuntime;
if (pythonRuntime !== undefined) {
  const destinationRoot = pythonRuntime.destination;
  if (
    typeof destinationRoot !== "string" ||
    !destinationRoot.startsWith("apps/reviewmatic/") ||
    !destinationRoot.endsWith("/portable") ||
    destinationRoot.includes("..")
  )
    throw new Error("invalid Python runtime destination");
  const entries = pythonRuntime.entries;
  if (!Array.isArray(entries) || entries.length === 0)
    throw new Error("Python runtime entries must be a non-empty list");
  const materialized = new Map();
  const targets = new Set();
  const unsafeTarget = new Set(["", ".", ".."]);
  for (const entry of entries) {
    const { source: entrySource, target } = entry;
    if (typeof target !== "string" || target.split("/").some((part) => unsafeTarget.has(part)))
      throw new Error("invalid Python runtime target");
    if (targets.has(target)) throw new Error(`duplicate Python runtime target: ${target}`);
    targets.add(target);
    const content = await readFile(resolve(root, "shared", entrySource));
    materialized.set(join(resolve(root, destinationRoot), target), content);
  }
  const existing = new Set();
  const collect = async (directory) => {
    for (const item of await readdir(directory, { withFileTypes: true })) {
      if (item.name === "__pycache__") continue; // CPython bytecode cache, not source
      const path = join(directory, item.name);
      if (item.isDirectory()) await collect(path);
      else if (item.isFile()) existing.add(path);
      else throw new Error(`unexpected non-regular materialized entry: ${path}`);
    }
  };
  const resolvedRoot = resolve(root, destinationRoot);
  try {
    await collect(resolvedRoot);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const changed = [];
  for (const [path, content] of materialized) {
    const current = existing.has(path) ? await readFile(path) : null;
    if (current === null || !current.equals(content)) changed.push(path);
    existing.delete(path);
  }
  if (existing.size > 0)
    throw new Error(`unexpected files in the Python runtime package: ${[...existing].join(", ")}`);
  if (process.argv.includes("--check")) {
    if (changed.length > 0) throw new Error(`shared Python runtime drift: ${changed.join(", ")}`);
  } else {
    for (const path of changed) {
      await mkdir(dirname(path), { recursive: true });
      const temporary = `${path}.${process.pid}.tmp`;
      await writeFile(temporary, materialized.get(path));
      await rename(temporary, path);
    }
  }
}
