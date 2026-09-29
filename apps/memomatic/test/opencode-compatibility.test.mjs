import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import { OpenCodeExecutor } from "../dist/executor.js";
import { planIngestion } from "../dist/ingestion.js";
import { MemoryStore } from "../dist/store.js";

test("OpenCode executor reuses an isolated server, denies tools and accounts actual usage", async () => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-executor-"));
  let executor;
  try {
    const binary = join(root, "opencode");
    writeFileSync(
      binary,
      `#!${process.execPath}
const assert = require("node:assert/strict");
assert.deepEqual(process.argv.slice(2), ["serve", "--hostname", "127.0.0.1", "--port", "0", "--pure"]);
assert.equal(JSON.parse(process.env.OPENCODE_CONFIG_CONTENT).permission,"deny");
let sessions=0;
const server=require("node:http").createServer(async(req,res)=>{
let body="";for await(const chunk of req)body+=chunk;
const value=JSON.parse(body);res.setHeader("Content-Type","application/json");
if(req.url==="/session"){assert.equal(value.permission[0].action,"deny");res.end(JSON.stringify({id:"session-"+(++sessions)}));return;}
assert.equal(value.system,"System");assert.deepEqual(value.model,{providerID:"provider",modelID:"model"});
assert.equal(value.variant,"fast");assert.equal(value.tools["*"],false);
res.end(JSON.stringify({info:{tokens:{input:10,output:2}},parts:[{type:"tool",text:'{"wrong":true}'},{type:"text",text:'{"candidates":[]}'}]}));
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
    assert.equal(executor.usage.inputTokens, 20);
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
    rmSync(root, { recursive: true, force: true });
  }
});

test("session ingestion preserves the normalized OpenCode part table and does not lose the tail", async () => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-ingest-"));
  const file = join(root, "opencode.db");
  try {
    const db = new DatabaseSync(file);
    db.exec(`
      CREATE TABLE session(id TEXT, title TEXT, directory TEXT, time_created INTEGER);
      CREATE TABLE message(id TEXT, session_id TEXT, data TEXT, time_created INTEGER);
      CREATE TABLE part(id TEXT, message_id TEXT, data TEXT, time_created INTEGER);
    `);
    const session = db.prepare("INSERT INTO session VALUES (?, ?, ?, ?)");
    const message = db.prepare("INSERT INTO message VALUES (?, ?, ?, ?)");
    const part = db.prepare("INSERT INTO part VALUES (?, ?, ?, ?)");
    session.run("normal", "Decision", "/workspace", 100);
    session.run("internal", "Dream", "/workspace", 200);
    message.run("user", "normal", '{"role":"user"}', 100);
    message.run("assistant", "normal", '{"role":"assistant"}', 101);
    message.run("dream", "internal", '{"role":"user"}', 200);
    part.run("b", "user", '{"type":"text","text":"Second"}', 102);
    part.run("a", "user", '{"type":"text","text":"First"}', 101);
    part.run("c", "user", '{"type":"tool","text":"Do not ingest"}', 103);
    part.run("d", "user", "invalid JSON", 104);
    part.run("e", "assistant", '{"type":"text","text":"Answer"}', 105);
    part.run("f", "dream", '{"type":"text","text":"[memomatic-internal] Extraction"}', 200);
    db.close();
    const store = await MemoryStore.open(":memory:");
    try {
      const plan = planIngestion(file, store, { before: 1000, maxChars: 256 });
      assert.equal(plan.sessions, 1);
      assert.match(plan.fragments[0].text, /First\nSecond/);
      assert.match(plan.fragments[0].text, /Answer/);
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
