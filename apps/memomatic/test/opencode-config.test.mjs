import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { isolatedProviderConfig } from "../dist/opencode-config.js";
import { opencodeDatabasePath } from "../dist/ingest.js";

test("private V2 config copies only provider settings and policies, preserving relative file references", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-v2-config-"));
  const saved = Object.fromEntries(
    ["OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT"].map((key) => [
      key,
      process.env[key],
    ]),
  );
  t.after(() => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    rmSync(root, { recursive: true, force: true });
  });
  process.env.OPENCODE_CONFIG_DIR = root;
  delete process.env.OPENCODE_CONFIG;
  process.env.OPENCODE_CONFIG_CONTENT =
    '{"providers":{"custom":{"settings":{"headers":{"X-Test":"keep"}}}},"plugins":["inline-user-plugin"],"experimental":{"policies":[{"action":"provider.use","resource":"allowed","effect":"allow"}]}}';
  const source = `{
    // private provider settings
    "providers": {"custom":{"settings":{"apiKey":"{file:provider.key}","baseURL":"https://example.invalid"}}},
    "plugins":["never-load-user-plugin"],
    "skills":["never-load-user-skills"],
    "mcp":{"servers":{"private":{"type":"remote","url":"https://private.invalid"}}},
    "agents":{"memomatic":{"permissions":[{"action":"*","resource":"*","effect":"allow"}]}},
    "experimental":{"policies":[{"action":"provider.use","resource":"blocked","effect":"deny"}]},
  }`;
  const file = join(root, "opencode.jsonc");
  writeFileSync(file, source);
  const config = await isolatedProviderConfig();
  assert.equal(config.providers.custom.settings.apiKey, `{file:${join(root, "provider.key")}}`);
  assert.equal(config.providers.custom.settings.baseURL, "https://example.invalid");
  assert.equal(config.providers.custom.settings.headers["X-Test"], "keep");
  assert.deepEqual(
    config.experimental.policies.map((rule) => rule.effect),
    ["deny", "allow"],
  );
  for (const key of ["plugins", "skills", "mcp", "agents"]) assert.equal(config[key], undefined);
  assert.equal((await import("node:fs")).readFileSync(file, "utf8"), source);
  writeFileSync(file, "invalid secret config content");
  await assert.rejects(
    isolatedProviderConfig(),
    (error) => /not valid JSON/.test(error.message) && !error.message.includes("secret config"),
  );
});

test("V2 database overrides resolve under the data directory and in-memory databases are rejected", (t) => {
  const saved = { OPENCODE_DB: process.env.OPENCODE_DB, XDG_DATA_HOME: process.env.XDG_DATA_HOME };
  t.after(() => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
  process.env.XDG_DATA_HOME = "/example/data";
  process.env.OPENCODE_DB = "preview.db";
  assert.equal(opencodeDatabasePath(), "/example/data/opencode/preview.db");
  process.env.OPENCODE_DB = "/example/custom.db";
  assert.equal(opencodeDatabasePath(), "/example/custom.db");
  process.env.OPENCODE_DB = ":memory:";
  assert.throws(opencodeDatabasePath, /in-memory/);
});
