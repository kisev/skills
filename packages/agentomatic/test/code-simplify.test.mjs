import assert from "node:assert/strict";
import test from "node:test";

import { CODE_SIMPLIFY_ROLES, codeSimplify } from "../dist/plugins/code-simplify.js";

async function injected(hooks, agent) {
  assert.deepEqual(Object.keys(hooks), ["context"]);
  const system = [];
  const event = { system };
  if (agent !== undefined) event.agent = agent;
  await hooks.context(event);
  await hooks.context(event);
  assert.ok(system.length <= 1, "repeated context hooks must stay idempotent");
  return system.length ? system[0].text : undefined;
}

test("level selects the injected compact rules", async () => {
  const lite = await injected(codeSimplify({ level: "lite" }), "worker");
  assert.match(lite, /\[code-simplify level=lite\]/);
  assert.match(lite, /necessity; 2\) existing code; 3\) standard library/);
  assert.doesNotMatch(lite, /report-only/);

  const full = await injected(codeSimplify(), "worker");
  assert.match(full, /\[code-simplify level=full\]/);
  assert.match(full, /delete\/stdlib\/native\/reuse\/yagni\/shrink/);
  assert.doesNotMatch(full, /dynamic references/);

  const ultra = await injected(codeSimplify({ level: "ultra" }), "worker");
  assert.match(ultra, /\[code-simplify level=ultra\]/);
  assert.match(ultra, /dynamic references/);
  assert.match(ultra, /trust boundary/);
});

test("invariant wording keeps the targeted caller search outside scanning", async () => {
  const full = await injected(codeSimplify(), "worker");
  assert.match(full, /never scan repositories or unrelated files/);
  assert.match(
    full,
    /a targeted caller search by exact name for code you are changing is not scanning/,
  );
  assert.match(full, /Never cancel a clarification or confirmation gate/);
});

test("default scope injects every role as before the option existed", async () => {
  const hooks = codeSimplify();
  for (const agent of [...CODE_SIMPLIFY_ROLES, "critic-security", "general", undefined]) {
    const text = await injected(hooks, agent);
    assert.match(text, /\[code-simplify level=full\]/, `agent=${agent}`);
  }
});

test("scope limits the injection to the listed fixed roles", async () => {
  const hooks = codeSimplify({ scope: ["worker", "review", "critic"] });
  for (const agent of ["worker", "review", "critic", "critic-coverage"]) {
    const text = await injected(hooks, agent);
    assert.match(text, /\[code-simplify level=full\]/, `agent=${agent} must stay injected`);
  }
  for (const agent of ["manager", "architect", "mapper", "general", undefined]) {
    const text = await injected(hooks, agent);
    assert.equal(text, undefined, `agent=${agent} must not be injected`);
  }
});

test("scope validates its roles against the catalog", () => {
  assert.deepEqual(
    [...CODE_SIMPLIFY_ROLES],
    ["manager", "architect", "mapper", "worker", "review", "critic"],
  );
  assert.throws(() => codeSimplify({ scope: ["worker", "builder"] }), /scope must list roles/);
});

test("off disables the wrapper completely", () => {
  assert.deepEqual(codeSimplify({ level: "off" }), {});
});
