import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";

const packed = JSON.parse(
  execFileSync("npm", ["pack", "--dry-run", "--json"], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  }),
)[0];
const files = packed.files.map(({ path }) => path).sort();
const allowed = ["README.md", "package.json"];

assert.ok(files.includes("README.md"));
assert.ok(files.includes("package.json"));
assert.ok(files.some((path) => path.startsWith("assets/")));
assert.ok(files.some((path) => path.startsWith("dist/")));
for (const path of files) {
  assert.ok(
    allowed.includes(path) || path.startsWith("assets/") || path.startsWith("dist/"),
    `unexpected packed file: ${path}`,
  );
}
process.stdout.write(`npm pack allowlist passed for ${files.length} files\n`);
