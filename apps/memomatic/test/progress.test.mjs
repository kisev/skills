import assert from "node:assert/strict";
import test from "node:test";
import { reporter } from "../dist/generated/cli.js";
test("terminal progress shows a known count bar, while JSON logs never emit animation", async (t) => {
  const output = [];
  t.mock.method(process.stderr, "write", (chunk) => {
    output.push(String(chunk));
    return true;
  });
  const log = reporter({ progress: "always", color: "never" });
  try {
    log.emit({ phase: "ingestion.extract", message: "Preparing work", total: 4, completed: 2 });
    log.emit({ phase: "model.wait", message: "Waiting for model" });
    await new Promise((resolve) => setTimeout(resolve, 180));
  } finally {
    log.close();
  }
  assert.match(output.join(""), /ingestion \[█+░+\] 50%/);
  output.length = 0;
  const json = reporter({ progress: "always", logFormat: "json" });
  json.emit({ phase: "model.wait", message: "Waiting" });
  json.close();
  assert.equal(output.length, 1);
  assert.equal(JSON.parse(output[0]).phase, "model.wait");
  assert.equal(output[0].includes("\u001b"), false);
});
