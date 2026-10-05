import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { integrationInstallCommands, skillInstallCommands } from "../src/install-commands.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const readme = await readFile(path.join(repoRoot, "README.md"), "utf8");

// The README install blocks are the canon for the site-rendered commands, so
// the test parses the README from the repository root (same precedent as
// sync.test.mjs) instead of restating the commands here.
function readmeInstallBlock(channel) {
  const blocks = [...readme.matchAll(/```shell\n(.*?)```/gs)].map((match) => match[1]);
  const block = blocks.find((candidate) =>
    candidate.includes(
      `npx --yes skills@latest add https://kisev.github.io/skills${channel === "dev" ? "/dev" : ""} --global`,
    ),
  );
  assert.ok(block, `README has no ${channel} install block`);
  return block;
}

function commands(block) {
  return block
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "" && !line.startsWith("#"));
}

for (const channel of ["latest", "dev"]) {
  test(`${channel} install commands match the README block exactly`, () => {
    assert.deepEqual(
      commands(integrationInstallCommands(channel)),
      commands(readmeInstallBlock(channel)),
    );
  });
}

test("single-skill installation projects the README commands to project scope", () => {
  const [preview, install, verify] = skillInstallCommands("code-review").split("\n\n");
  const latest = commands(readmeInstallBlock("latest"));
  const add = latest.find((line) => line.startsWith("npx --yes skills@latest add"));
  assert.ok(add !== undefined);
  const source = add.split(" ")[4];
  assert.equal(commands(install)[0], `npx --yes skills@latest add ${source} --skill code-review`);
  assert.equal(
    commands(preview)[0],
    latest.find((line) => line.startsWith("npm view --prefer-online skills@latest")),
  );
  const globalVerify = latest.find((line) => line.startsWith("npx --yes skills@latest list"));
  assert.ok(globalVerify !== undefined);
  assert.equal(commands(verify)[0], globalVerify.replace(/ --global$/, ""));
});
