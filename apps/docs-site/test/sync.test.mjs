import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { collectCatalog, parseRuSkillDescriptions } from "../scripts/sync-content.mjs";

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ruCatalogPath = path.join(
  siteRoot,
  "..",
  "..",
  "docs",
  "ru",
  "reference",
  "skill-catalog.md",
);
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

test("the RU catalog parser reads slug descriptions from the active-skills table", () => {
  const descriptions = parseRuSkillDescriptions(
    [
      "# Каталог навыков",
      "## Активные навыки",
      "",
      "| Навык | Назначение |",
      "| - | - |",
      "| `alpha` | Первое назначение. |",
      "| `beta` | Второе назначение. |",
      "",
      "## Следующая секция",
    ].join("\n"),
  );
  assert.deepEqual(
    [...descriptions.entries()],
    [
      ["alpha", "Первое назначение."],
      ["beta", "Второе назначение."],
    ],
  );
});

test("the RU catalog parser fails loudly on structural drift", () => {
  assert.throws(
    () => parseRuSkillDescriptions("# Каталог без таблицы\n"),
    /no ## Активные навыки section/,
  );
  assert.throws(
    () => parseRuSkillDescriptions("## Активные навыки\n\n| Навык | Назначение |\n| - | - |\n"),
    /no rows/,
  );
  assert.throws(
    () =>
      parseRuSkillDescriptions(
        "## Активные навыки\n\n| `alpha` | Первое. |\n| `alpha` | Повтор. |\n",
      ),
    /duplicate RU skill catalog row: alpha/,
  );
  assert.throws(
    () => parseRuSkillDescriptions("## Активные навыки\n\n| `alpha` |  |\n"),
    /empty RU description/,
  );
});

test("every catalog skill carries the RU description from the catalog table", async () => {
  const catalog = await collectCatalog();
  const table = parseRuSkillDescriptions(await readFile(ruCatalogPath, "utf8"));
  assert.ok(catalog.skills.length > 0);
  for (const skill of catalog.skills) {
    assert.ok(
      typeof skill.descriptionRu === "string" && skill.descriptionRu.length > 0,
      `${skill.name}: missing RU description`,
    );
    assert.equal(
      skill.descriptionRu,
      table.get(skill.name),
      `${skill.name}: RU description diverged from the catalog table`,
    );
  }
  assert.equal(
    table.size,
    catalog.skills.length,
    "RU catalog table and skill directories cover different sets",
  );
});

test("RU pages render the catalog descriptions instead of English ones", async () => {
  const catalog = await collectCatalog();
  assert.ok(catalog.skills.length > 0);
  for (const relative of [
    "src/components/SkillCard.astro",
    "src/pages/ru/skills/[skill].astro",
    "src/pages/ru/examples/index.astro",
  ]) {
    const source = await readFile(path.join(siteRoot, relative), "utf8");
    assert.ok(
      source.includes("descriptionRu"),
      `${relative}: renders the English description on RU pages`,
    );
  }
  const card = await readFile(path.join(siteRoot, "src/components/SkillCard.astro"), "utf8");
  assert.match(card, /locale === "ru" \? skill\.descriptionRu : skill\.description/);
});
