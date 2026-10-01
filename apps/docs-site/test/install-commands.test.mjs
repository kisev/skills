import assert from "node:assert/strict";
import test from "node:test";
import { integrationInstallCommands, skillInstallCommands } from "../src/install-commands.mjs";

for (const channel of ["latest", "dev"]) {
  test(`${channel} installation previews registry versions and checks the owning project`, () => {
    const [preview, install, verify] = integrationInstallCommands(channel).split("\n\n");
    assert.match(preview, /npm view --prefer-online skills@latest version/);
    assert.ok(preview.includes(`npm view --prefer-online @kisev/agentomatic@${channel} version`));
    const source = `https://kisev.github.io/skills${channel === "dev" ? "/dev" : ""}`;
    assert.ok(install.includes(`npx --yes skills@latest add ${source} --global`));
    assert.ok(install.includes(`npx --yes @kisev/agentomatic@${channel} install --global`));
    assert.match(
      verify,
      /npm list --prefix "\$HOME\/\.config\/opencode" @kisev\/agentomatic --depth=0/,
    );
    assert.match(verify, /npx --yes skills@latest list --global/);
    assert.doesNotMatch(verify, /--version|npm list --global/);
  });
}

test("single-skill installation verifies the same project scope", () => {
  const [preview, install, verify] = skillInstallCommands("code-review").split("\n\n");
  assert.match(preview, /npm view --prefer-online skills@latest version/);
  assert.match(install, /skills@latest add https:\/\/kisev.github.io\/skills --skill code-review/);
  assert.match(verify, /npx --yes skills@latest list$/);
  assert.doesNotMatch(verify, /--version|--global/);
});
