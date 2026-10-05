import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { COMMAND_REGISTRY, COMMANDLESS_SKILLS } from "../dist/registry.js";
import { CATALOG } from "../dist/catalog.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "..", "..");

const skillDirectories = readdirSync(resolve(repositoryRoot, "skills"), {
  withFileTypes: true,
})
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);
const publicSurfaces = JSON.parse(
  readFileSync(resolve(repositoryRoot, "evals", "contracts", "public-surfaces.json"), "utf8"),
);
const migrationInventory = JSON.parse(
  readFileSync(resolve(packageRoot, "assets", "migration-inventory.json"), "utf8"),
);
const skillCommands = COMMAND_REGISTRY.filter((command) => "skill" in command);
const packageCommands = COMMAND_REGISTRY.filter((command) => !("skill" in command));

const commandless = [...COMMANDLESS_SKILLS];
const commandedSkills = skillDirectories.filter((name) => !commandless.includes(name));

function expectSameSkills(surface, values) {
  const expected = [...skillDirectories].sort();
  const actual = [...values].sort();
  assert.deepEqual(
    actual,
    expected,
    `${surface} drifts from skills/ directories: missing ${
      expected.filter((name) => !actual.includes(name)).join(", ") || "none"
    }, unexpected ${actual.filter((name) => !expected.includes(name)).join(", ") || "none"}`,
  );
}

function expectSameCommands(surface, values) {
  const expected = commandedSkills.sort();
  const actual = [...values].sort();
  assert.deepEqual(
    actual,
    expected,
    `${surface} drifts from command-owning skills: missing ${
      expected.filter((name) => !actual.includes(name)).join(", ") || "none"
    }, unexpected ${actual.filter((name) => !expected.includes(name)).join(", ") || "none"}`,
  );
}

test("every authored skill directory has the authored entrypoint", () => {
  for (const name of skillDirectories) {
    assert.ok(existsSync(resolve(repositoryRoot, "skills", name, "SKILL.source.md")), name);
  }
});

test("every skill directory is wired into every package surface inventory", () => {
  expectSameSkills("CATALOG.skills", CATALOG.skills);
  expectSameSkills("public-surfaces skills", publicSurfaces.skills);
  expectSameSkills(
    "migration-inventory active_portable_skills",
    migrationInventory.active_portable_skills,
  );
  expectSameCommands(
    "registry skill commands",
    skillCommands.map((command) => command.skill),
  );
  expectSameCommands("migration-inventory active_commands", migrationInventory.active_commands);
});

test("commandless skills own no command adapter anywhere", () => {
  assert.ok(commandless.length > 0, "the commandless list must not silently empty out");
  const commandSkills = new Set(skillCommands.map((command) => command.skill));
  for (const name of commandless) {
    assert.ok(skillDirectories.includes(name), `${name} must be an authored skill`);
    assert.ok(!commandSkills.has(name), `${name} must not own a command adapter`);
    const frontmatter = readFileSync(
      resolve(repositoryRoot, "skills", name, "SKILL.source.md"),
      "utf8",
    );
    assert.match(frontmatter, /^  command: "false"$/m, `${name} frontmatter label`);
    assert.match(frontmatter, /^  inspired-by:/m, `${name} inspired-by label`);
  }
  // Every skill either owns its one-to-one command or carries the label.
  assert.equal(commandSkills.size + commandless.length, skillDirectories.length);
});

test("skill commands stay one-to-one with their skills", () => {
  for (const command of skillCommands) {
    assert.equal(command.name, command.skill, command.name);
  }
});

test("command registry matches the public surface contract exactly", () => {
  assert.deepEqual(
    COMMAND_REGISTRY.map((command) => command.name).sort(),
    [...publicSurfaces.commands].sort(),
    "COMMAND_REGISTRY must mirror public-surfaces.json commands",
  );
  assert.deepEqual(
    packageCommands.map((command) => command.name).sort(),
    [...CATALOG.package_commands].sort(),
    "package commands must mirror CATALOG.package_commands",
  );
});
