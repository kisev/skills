// Coverage contract for the Russian overlay of shared relation reasons. The
// shared contract (shared/skill-relations.json) stays English-only; the site
// overlay must translate every documented reason and nothing else.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { collectCatalog } from "../scripts/sync-content.mjs";

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const overlayPath = path.join(siteRoot, "src", "i18n", "relation-reasons.ru.json");

const overlayKey = (relation) => `${relation.from}|${relation.to}|${relation.type}`;

test("every documented relation reason has a Russian overlay entry", async () => {
  const catalog = await collectCatalog();
  const documented = catalog.relations.filter((relation) => relation.reason !== "");
  assert.ok(documented.length > 0);
  const overlay = JSON.parse(await readFile(overlayPath, "utf8"));
  for (const relation of documented) {
    const translated = overlay[overlayKey(relation)];
    assert.ok(
      typeof translated === "string" && translated.length > 0,
      `missing RU reason overlay: ${overlayKey(relation)}`,
    );
    assert.notEqual(
      translated,
      relation.reason,
      `RU reason overlay is an untranslated copy: ${overlayKey(relation)}`,
    );
  }
});

test("the overlay translates nothing beyond documented relations", async () => {
  const catalog = await collectCatalog();
  const documented = new Set(
    catalog.relations.filter((relation) => relation.reason !== "").map(overlayKey),
  );
  const overlay = JSON.parse(await readFile(overlayPath, "utf8"));
  for (const key of Object.keys(overlay)) {
    assert.ok(documented.has(key), `overlay entry has no documented relation: ${key}`);
  }
  assert.equal(
    Object.keys(overlay).length,
    documented.size,
    "overlay and documented reasons cover different counts",
  );
});
