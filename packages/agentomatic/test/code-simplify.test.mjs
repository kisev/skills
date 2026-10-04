import assert from "node:assert/strict";
import test from "node:test";

import { codeSimplify } from "../dist/plugins/code-simplify.js";

async function injected(hooks) {
  assert.deepEqual(Object.keys(hooks), ["context"]);
  const system = [];
  await hooks.context({ system });
  await hooks.context({ system });
  assert.equal(system.length, 1, "repeated context hooks must stay idempotent");
  return system[0].text;
}

test("level selects the injected compact rules", async () => {
  const lite = await injected(codeSimplify({ level: "lite" }));
  assert.match(lite, /\[code-simplify level=lite\]/);
  assert.match(lite, /necessity; 2\) existing code; 3\) standard library/);
  assert.doesNotMatch(lite, /report-only/);

  const full = await injected(codeSimplify());
  assert.match(full, /\[code-simplify level=full\]/);
  assert.match(full, /delete\/stdlib\/native\/reuse\/yagni\/shrink/);
  assert.doesNotMatch(full, /dynamic references/);

  const ultra = await injected(codeSimplify({ level: "ultra" }));
  assert.match(ultra, /\[code-simplify level=ultra\]/);
  assert.match(ultra, /dynamic references/);
  assert.match(ultra, /trust boundary/);
});

test("off disables the wrapper completely", () => {
  assert.deepEqual(codeSimplify({ level: "off" }), {});
});
