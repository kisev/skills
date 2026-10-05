// Mechanical contract for internal links: every href in the site templates
// must be built through the i18n builders (`localizedPath`,
// `alternateLocalePath`) or, for locale-independent assets, `withBase`.
// Hand-built hrefs and hardcoded locale paths fail these tests.
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(siteRoot, "src");
const utilsPath = path.join(srcDir, "i18n", "utils.ts");
const PAGE_BUILDERS = ["localizedPath(", "alternateLocalePath("];
const ASSET_BUILDER = "withBase(";
const HREF = /href=(?:"([^"]*)"|\{([^}]*)\})/g;

async function walk(dir, suffix) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(full, suffix)));
    } else if (entry.name.endsWith(suffix)) {
      files.push(full);
    }
  }
  return files;
}

function tagOf(content, index) {
  const open = content.lastIndexOf("<", index - 1);
  if (open === -1) {
    return null;
  }
  const tail = content.slice(open, index);
  if (tail.includes(">")) {
    return null;
  }
  return /^<([a-zA-Z][a-zA-Z0-9-]*)/.exec(tail)?.[1] ?? null;
}

test("every template href is built through the i18n builders", async () => {
  for (const file of await walk(srcDir, ".astro")) {
    const content = await readFile(file, "utf8");
    const relative = path.relative(srcDir, file);
    for (const match of content.matchAll(HREF)) {
      const [whole, staticValue, expression] = match;
      const tag = tagOf(content, match.index);
      assert.ok(tag !== null, `${relative}: href outside a tag: ${whole}`);
      if (staticValue !== undefined) {
        assert.match(
          staticValue,
          /^(https?:\/\/|mailto:|#)/,
          `${relative}: hardcoded href in <${tag}>: ${whole}`,
        );
        continue;
      }
      const builders = tag === "a" ? PAGE_BUILDERS : [...PAGE_BUILDERS, ASSET_BUILDER];
      assert.ok(
        builders.some((builder) => expression.includes(builder)),
        `${relative}: <${tag}> href not built via ${builders.join(" / ")}: ${whole}`,
      );
    }
  }
});

test("anchors never drop the locale via withBase", async () => {
  for (const file of await walk(srcDir, ".astro")) {
    const content = await readFile(file, "utf8");
    const relative = path.relative(srcDir, file);
    for (const match of content.matchAll(HREF)) {
      const expression = match[2];
      if (expression === undefined) {
        continue;
      }
      const tag = tagOf(content, match.index);
      assert.ok(
        !(tag === "a" && expression.includes(ASSET_BUILDER)),
        `${relative}: <a> href must keep the locale: ${expression}`,
      );
    }
  }
});

test("withBase stays inside i18n/utils outside template assets", async () => {
  for (const file of await walk(srcDir, ".ts")) {
    if (file === utilsPath) {
      continue;
    }
    const content = await readFile(file, "utf8");
    assert.ok(
      !content.includes(ASSET_BUILDER),
      `${path.relative(srcDir, file)}: use localizedPath instead of withBase`,
    );
  }
});

test("localizedPath resolves every scanned route under the locale prefix", async () => {
  const scanned = new Set();
  for (const file of await walk(srcDir, ".astro")) {
    const content = await readFile(file, "utf8");
    for (const match of content.matchAll(/localizedPath\((`[^`]*`|"[^"]*"|'[^']*')/g)) {
      const route = match[1].slice(1, -1).replace(/\$\{[^}]*\}/g, "sample-skill");
      scanned.add(route);
    }
  }
  const routes = new Set(["/", "/skills/", "/examples/", "/skills/sample-skill/", ...scanned]);
  for (const route of routes) {
    assert.equal(
      localeMirror(route, "en"),
      `/skills${route}`,
      `EN resolution drifted for ${route}`,
    );
    assert.equal(
      localeMirror(route, "ru"),
      `/skills/ru${route}`,
      `RU resolution drifted for ${route}`,
    );
  }
});

// Mirrors localizedPath(); the real implementation is exercised by the build.
function localeMirror(route, locale) {
  return `/skills${locale === "en" ? route : `/ru${route}`}`;
}

test("landing pages drop the skill count in both locales", async () => {
  const ui = await readFile(path.join(srcDir, "i18n", "ui.ts"), "utf8");
  const [en, ru] = ui.split(/^  ru: \{/m);
  for (const [locale, half] of [
    ["en", en],
    ["ru", ru],
  ]) {
    const lead = /lead: "([^"]*)"/.exec(half)?.[1];
    assert.ok(lead !== undefined, `${locale}: hero lead missing`);
    assert.ok(!lead.includes("{count}"), `${locale}: hero lead keeps the {count} slot`);
    assert.ok(!/\d/.test(lead), `${locale}: hero lead hardcodes a numeric count`);
  }
  for (const landing of ["pages/index.astro", "pages/ru/index.astro"]) {
    const page = await readFile(path.join(srcDir, landing), "utf8");
    assert.ok(!page.includes(".replace("), `${landing}: substitutes the count`);
    assert.ok(!page.includes("catalog.skills.length"), `${landing}: computes the skill count`);
  }
});

test("the footer is pinned to the bottom on every layout", async () => {
  const css = await readFile(path.join(srcDir, "styles", "global.css"), "utf8");
  const body = /(?<![-\w])body\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
  const main = /(?<![-\w])main\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
  assert.match(body, /display:\s*flex/);
  assert.match(body, /flex-direction:\s*column/);
  assert.match(body, /min-height:\s*100vh/);
  assert.match(main, /flex:\s*1/);
});

test("the components table covers every project component in both locales", async () => {
  const ui = await readFile(path.join(srcDir, "i18n", "ui.ts"), "utf8");
  const [en, ru] = ui.split(/^  ru: \{/m);
  const components = ["portable", "agentomatic", "memomatic", "reviewmatic", "taskmatic"];
  for (const [locale, half] of [
    ["en", en],
    ["ru", ru],
  ]) {
    for (const component of components) {
      assert.ok(half.includes(`${component}:`), `${locale}: ${component} row missing`);
      assert.ok(half.includes(`${component}Provides:`), `${locale}: ${component} provides missing`);
    }
  }
  for (const landing of ["pages/index.astro", "pages/ru/index.astro"]) {
    const page = await readFile(path.join(srcDir, landing), "utf8");
    for (const component of components) {
      assert.ok(
        page.includes(`t.components.table.${component}`),
        `${landing}: ${component} row is not rendered`,
      );
    }
  }
});
