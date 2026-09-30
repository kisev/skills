import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import { OpenCodeExecutor } from "../dist/executor.js";
import { planIngestion } from "../dist/ingestion.js";
import { MemoryStore } from "../dist/store.js";
import { createSessionTables, insertMessage } from "./opencode-fixture.mjs";

test("OpenCode V2 executor reuses an isolated server, denies tools and marks unavailable usage", async () => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-executor-"));
  const saved = Object.fromEntries(
    ["OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT"].map((key) => [
      key,
      process.env[key],
    ]),
  );
  process.env.OPENCODE_CONFIG_DIR = root;
  delete process.env.OPENCODE_CONFIG;
  delete process.env.OPENCODE_CONFIG_CONTENT;
  let executor;
  try {
    const binary = join(root, "opencode");
    writeFileSync(
      binary,
      `#!${process.execPath}
const assert = require("node:assert/strict");
assert.deepEqual(process.argv.slice(2), ["serve", "--hostname", "127.0.0.1", "--port", "0"]);
const config=JSON.parse(require("node:fs").readFileSync(process.env.OPENCODE_CONFIG,"utf8"));
assert.deepEqual(config.permissions,[{action:"*",resource:"*",effect:"deny"}]);
assert.equal(config.permission,undefined);assert.equal(config.agents.memomatic.mode,"primary");
assert.equal(process.env.OPENCODE_CONFIG_DIR,process.cwd());
let sessions=0;
const server=require("node:http").createServer(async(req,res)=>{
let body="";for await(const chunk of req)body+=chunk;
const value=JSON.parse(body);res.setHeader("Content-Type","application/json");
if(req.url==="/api/session"){assert.deepEqual(value.permissions,[{action:"*",resource:"*",effect:"deny"}]);assert.deepEqual(value.model,{providerID:"provider",id:"model",variant:"fast"});res.end(JSON.stringify({data:{id:"ses_"+(++sessions)}}));return;}
if(req.method==="PUT"){assert.match(req.url,/instructions\\/entries\\/memomatic$/);assert.equal(value.value,"System");res.writeHead(204);res.end();return;}
assert.match(req.url,/^\\/api\\/session\\/ses_\\d+\\/generate$/);assert.equal(typeof value.prompt,"string");assert.equal(value.tools,undefined);
res.end(JSON.stringify({data:{text:'{"candidates":[]}'}}));
});
const listen=()=>server.listen(0,"127.0.0.1",()=>console.log("opencode server listening on http://127.0.0.1:"+server.address().port));
if(process.platform==="linux") {
const helper=require("node:child_process").spawn(process.execPath,["-e","process.on('SIGTERM',()=>{});console.log(process.pid);setInterval(()=>{},10000)"],{stdio:["ignore","pipe","ignore"]});
helper.stdout.once("data",data=>{require("node:fs").writeFileSync(${JSON.stringify(join(root, "descendant"))},data.toString());listen();});
}else listen();
`,
      { mode: 0o700 },
    );
    executor = new OpenCodeExecutor({ binary, model: "provider/model", variant: "fast" });
    assert.equal(
      await executor.complete({ system: "System", prompt: "Prompt" }),
      '{"candidates":[]}',
    );
    const pid = executor.child.pid;
    await executor.complete({ system: "System", prompt: "Another prompt" });
    assert.equal(executor.child.pid, pid);
    assert.equal(executor.usage.calls, 2);
    assert.equal(executor.usage.inputTokens, 0);
    assert.equal(executor.usage.usageAvailable, false);
    await executor.close();
    assert.throws(() => process.kill(pid, 0));
    if (process.platform === "linux") {
      const descendant = Number(readFileSync(join(root, "descendant"), "utf8").trim());
      let stopped = false;
      for (let attempt = 0; attempt < 50; attempt++) {
        try {
          stopped = /\) Z /.test(readFileSync(`/proc/${descendant}/stat`, "utf8"));
        } catch {
          stopped = true;
        }
        if (stopped) break;
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
      assert.ok(stopped, "owned descendant survived executor shutdown");
    }
  } finally {
    await executor?.close();
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    rmSync(root, { recursive: true, force: true });
  }
});

test("session ingestion reads only native V2 text projections in sequence order", async () => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-ingest-"));
  const file = join(root, "opencode.db");
  try {
    const db = new DatabaseSync(file);
    createSessionTables(db);
    const session = db.prepare("INSERT INTO session_v2 VALUES (?, ?, ?, ?, ?)");
    session.run("normal", "Decision", "/workspace", 100, 100);
    session.run("internal", "Dream", "/workspace", 200, 200);
    insertMessage(db, "z", "normal", "user", "First", 1);
    insertMessage(db, "a", "normal", "user", "Second", 2);
    const message = db.prepare("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)");
    message.run(
      "assistant",
      "normal",
      "assistant",
      3,
      JSON.stringify({
        content: [
          { type: "text", text: "Answer" },
          { type: "tool", text: "Do not ingest" },
          { type: "reasoning", text: "Private reasoning" },
          { type: "text", text: "Final decision" },
        ],
      }),
      1,
      1,
    );
    message.run("invalid", "normal", "assistant", 4, "invalid JSON", 1, 1);
    message.run(
      "synthetic",
      "normal",
      "synthetic",
      5,
      '{"text":"Do not ingest synthetic instructions"}',
      1,
      1,
    );
    insertMessage(db, "dream", "internal", "user", "[memomatic-internal] Extraction", 1);
    db.close();
    const store = await MemoryStore.open(":memory:");
    try {
      const plan = planIngestion(file, store, { before: 1000, maxChars: 256 });
      assert.equal(plan.sessions, 1);
      assert.match(plan.fragments[0].text, /First[\s\S]*Second/);
      assert.match(plan.fragments[0].text, /Answer/);
      assert.match(plan.fragments[0].text, /Final decision/);
      assert.doesNotMatch(
        plan.fragments.map((fragment) => fragment.text).join("\n"),
        /Do not ingest|Private reasoning/,
      );
      for (const fragment of plan.fragments)
        for (const key of fragment.checkpointKeys) store.setMeta(key, fragment.id);
      assert.equal(planIngestion(file, store, { before: 1000, maxChars: 256 }).fragments.length, 0);
    } finally {
      store.close();
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
