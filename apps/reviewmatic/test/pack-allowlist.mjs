import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
const [pack] = JSON.parse(
  execFileSync("npm", ["pack", "--dry-run", "--json"], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  }),
);
const files = pack.files.map((item) => item.path);
for (const required of ["package.json", "README.md", "README.ru.md", "dist/cli.js"])
  assert.ok(files.includes(required));
for (const file of files)
  assert.ok(
    ["package.json", "README.md", "README.ru.md"].includes(file) || file.startsWith("dist/"),
    file,
  );
