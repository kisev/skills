import assert from "node:assert/strict";
import { readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { collectCatalog } from "../scripts/sync-content.mjs";

const skillsDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "skills",
);

test("catalog covers every portable skill directory exactly once", async () => {
  const catalog = await collectCatalog();
  const directories = (await readdir(skillsDir, { withFileTypes: true })).filter((entry) =>
    entry.isDirectory(),
  );
  const names = catalog.skills.map((skill) => skill.name);
  assert.equal(names.length, directories.length);
  assert.equal(new Set(names).size, names.length);
  assert.deepEqual([...names].sort(), names.sort());
});

test("every catalog entry carries a slug name and a description", async () => {
  const catalog = await collectCatalog();
  for (const skill of catalog.skills) {
    assert.match(skill.name, /^[a-z0-9][a-z0-9-]*$/);
    assert.ok(skill.description.length > 0);
  }
});

test("declared relations reference known skills with documented types", async () => {
  const catalog = await collectCatalog();
  const names = new Set(catalog.skills.map((skill) => skill.name));
  assert.ok(catalog.relations.length > 0);
  for (const relation of catalog.relations) {
    assert.ok(names.has(relation.from), `unknown relation source: ${relation.from}`);
    assert.ok(names.has(relation.to), `unknown relation target: ${relation.to}`);
    assert.ok(
      ["requires", "uses", "recommends"].includes(relation.type),
      `undeclared relation type: ${relation.type}`,
    );
  }
});
