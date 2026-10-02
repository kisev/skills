import { readFile, mkdir, writeFile, rename } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { execFileSync } from "node:child_process";
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
for (const schema of shared.npmSchemas ?? []) {
  if (
    schema.source !== "references/portable_gitlab/artifact-contracts-v2.schema.json" ||
    schema.destination !== "apps/reviewmatic/src/generated/artifact-schema.ts"
  )
    throw new Error("invalid schema materialization");
  const value = JSON.parse(await readFile(resolve(root, "shared", schema.source), "utf8"));
  const content = execFileSync("oxfmt", ["--stdin-filepath", schema.destination], {
    input: `export const ARTIFACT_SCHEMA_ID = ${JSON.stringify(value.$id)};\n\nexport const ARTIFACT_SCHEMA: Record<string, unknown> = ${JSON.stringify(value, null, 2)};\n`,
    encoding: "utf8",
  });
  const path = resolve(root, schema.destination);
  if (process.argv.includes("--check")) {
    if ((await readFile(path, "utf8")) !== content)
      throw new Error(`shared schema drift: ${schema.destination}`);
  } else {
    await mkdir(dirname(path), { recursive: true });
    const temporary = `${path}.${process.pid}.tmp`;
    await writeFile(temporary, content);
    await rename(temporary, path);
  }
}
