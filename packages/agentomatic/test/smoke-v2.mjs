import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "../../..");
const directory = await mkdtemp(join(tmpdir(), "agentomatic-smoke-v2-"));
const binary = process.env.OPENCODE_BINARY;
assert.ok(binary, "Set OPENCODE_BINARY to the pinned V2 executable");
let server;
try {
  const project = join(directory, "project");
  const home = join(directory, "home");
  await mkdir(project);
  await mkdir(home);
  await writeFile(join(project, "package.json"), '{"private":true}\n');
  const packed =
    process.env.AGENTOMATIC_TARBALL && process.env.SAFE_FS_TARBALL
      ? []
      : JSON.parse(
          execFileSync("npm", ["pack", "--json", "--workspaces", "--pack-destination", directory], {
            cwd: root,
            encoding: "utf8",
          }),
        );
  const tarball = (name, variable) =>
    process.env[variable] ?? join(directory, packed.find((entry) => entry.name === name).filename);
  execFileSync(
    "npm",
    [
      "install",
      "--ignore-scripts",
      tarball("@kisev/safe-fs", "SAFE_FS_TARBALL"),
      tarball("@kisev/agentomatic", "AGENTOMATIC_TARBALL"),
    ],
    { cwd: project, encoding: "utf8" },
  );
  const env = {
    PATH: process.env.PATH ?? "",
    HOME: home,
    XDG_CONFIG_HOME: join(home, ".config"),
    XDG_STATE_HOME: join(home, ".state"),
    XDG_DATA_HOME: join(home, ".data"),
    XDG_CACHE_HOME: join(home, ".cache"),
    OPENCODE_DISABLE_MODELS_FETCH: "true",
    OPENCODE_SERVER_PASSWORD: "agentomatic-smoke",
  };
  execFileSync(
    join(project, "node_modules/.bin/agentomatic"),
    [
      "install",
      "--commands",
      "none",
      "--agents",
      "manager,mapper,worker,review,architect,critic",
      "--plugins",
      "rtk,rules-injector,zed-bell",
      "--no-core",
      "--no-dependency",
      "--yes",
    ],
    { cwd: project, env, encoding: "utf8" },
  );
  assert.match(
    await readFile(join(project, ".opencode/plugins/rtk.js"), "utf8"),
    /export default plugin/,
  );
  await writeFile(
    join(project, ".opencode/opencode.json"),
    JSON.stringify({
      plugins: [pathToFileURL(join(project, "node_modules/@kisev/agentomatic/dist")).href],
      permissions: [
        { action: "read", resource: "*", effect: "ask" },
        { action: "external_directory", resource: "*", effect: "ask" },
      ],
    }),
  );
  execFileSync(
    join(project, "node_modules/.bin/agentomatic"),
    [
      "config",
      "--targets",
      "opencode",
      "--fragments",
      "skills-state-permissions,secrets-guard",
      "--no-dependency",
      "--yes",
    ],
    { cwd: project, env, encoding: "utf8" },
  );
  const configured = await readFile(join(project, ".opencode/opencode.json"), "utf8");
  execFileSync(
    join(project, "node_modules/.bin/agentomatic"),
    [
      "config",
      "--targets",
      "opencode",
      "--fragments",
      "skills-state-permissions,secrets-guard",
      "--no-dependency",
      "--yes",
    ],
    { cwd: project, env, encoding: "utf8" },
  );
  assert.equal(await readFile(join(project, ".opencode/opencode.json"), "utf8"), configured);
  let logs = "";
  server = spawn(
    binary,
    ["serve", "--hostname", "127.0.0.1", "--port", "0", "--print-logs", "--log-level", "debug"],
    { cwd: project, env, stdio: ["ignore", "pipe", "pipe"] },
  );
  const url = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`V2 startup timed out: ${logs}`)), 45_000);
    const observe = (chunk) => {
      logs += chunk.toString();
      const match = logs.match(/listening on (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {
        clearTimeout(timeout);
        resolve(match[1]);
      }
    };
    server.stdout.on("data", observe);
    server.stderr.on("data", observe);
    server.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    server.once("exit", (code) => {
      clearTimeout(timeout);
      reject(new Error(`V2 exited ${code}: ${logs}`));
    });
  });
  const get = async (path) => {
    const query = new URLSearchParams({ "location[directory]": project });
    const response = await fetch(`${url}${path}?${query}`, {
      headers: {
        authorization: `Basic ${Buffer.from("opencode:agentomatic-smoke").toString("base64")}`,
      },
      signal: AbortSignal.timeout(30_000),
    });
    assert.equal(response.status, 200, `${path}: ${await response.clone().text()}\n${logs}`);
    return response.json();
  };
  const post = async (path, body) => {
    const response = await fetch(`${url}${path}`, {
      method: "POST",
      headers: {
        authorization: `Basic ${Buffer.from("opencode:agentomatic-smoke").toString("base64")}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    });
    assert.equal(response.status, 200, `${path}: ${await response.clone().text()}\n${logs}`);
    return response.json();
  };
  await get("/api/location");
  const expected = [
    "agentomatic",
    "agentomatic.rtk",
    "agentomatic.rules-injector",
    "agentomatic.zed-bell",
  ];
  let listing;
  const deadline = Date.now() + 30_000;
  do {
    listing = await get("/api/plugin");
    if (expected.every((id) => listing.data.some((entry) => entry.id === id))) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  } while (Date.now() < deadline);
  assert.equal(listing.location.directory, project);
  const plugins = listing.data;
  const agents = (await get("/api/agent")).data;
  const diagnostics = logs
    .split("\n")
    .filter((line) => /plugin|WARN|ERROR/i.test(line))
    .join("\n");
  for (const id of [
    "agentomatic",
    "agentomatic.rtk",
    "agentomatic.rules-injector",
    "agentomatic.zed-bell",
  ]) {
    const plugin = plugins.find((entry) => entry.id === id);
    assert.ok(
      plugin,
      `Missing ${id}: ${JSON.stringify(plugins.filter((entry) => entry.source.type !== "builtin"))}\n${diagnostics}`,
    );
    assert.equal(plugin.state.status, "active", `${id}: ${JSON.stringify(plugin)}`);
  }
  assert.ok(agents.some((agent) => agent.id === "manager"));
  assert.ok(agents.some((agent) => agent.id === "mapper"));
  const mapper = agents.find((agent) => agent.id === "mapper");
  assert.ok(mapper.permissions.some((rule) => rule.action === "shell" && rule.effect === "deny"));
  const session = (await post("/api/session", { agent: "build", location: { directory: project } }))
    .data;
  const permission = async (action, resource, effect, agent = "build") => {
    const reply = await post(`/api/session/${session.id}/permission`, {
      action,
      resources: [resource],
      agent,
    });
    assert.equal(reply.data.effect, effect, `${action}: ${resource}`);
  };
  await permission("read", join(home, ".local/state/agent-skills/test.json"), "allow");
  await permission("edit", join(home, ".local/state/agent-skills/test.json"), "allow");
  await permission("external_directory", join(home, ".local/state/agent-skills/*"), "allow");
  await permission("read", join(home, ".config/opencode/skills/test/SKILL.md"), "allow");
  await permission("external_directory", join(home, ".config/opencode/skills/*"), "allow");
  for (const resource of [".env", "nested/.env", ".env.local", "nested/.ssh/id_rsa"]) {
    await permission("read", resource, "deny");
    await permission("edit", resource, "deny");
  }
  await permission("read", ".env.example", "allow");
  await permission("read", "nested/.env.example", "allow");
  await permission("edit", ".env.example", "deny");
  await permission("edit", "source.ts", "deny", "mapper");
  await permission("shell", "git push origin dev", "deny", "critic");
  await permission(
    "shell",
    "git --no-optional-locks -c core.fsmonitor=false status --porcelain=v1 --untracked-files=all",
    "allow",
    "critic",
  );
  await permission("subagent", "critic", "allow", "review");
  await permission("subagent", "worker", "deny", "review");
  assert.deepEqual((await get(`/api/session/${session.id}/permission`)).data, []);
  process.stdout.write(
    "Packed OpenCode V2 plugin loading, agent discovery, and permission evaluation smoke test passed\n",
  );
  {
    const exited = once(server, "exit");
    server.kill("SIGTERM");
    const timer = setTimeout(() => server.kill("SIGKILL"), 5000);
    await exited;
    clearTimeout(timer);
  }
  execFileSync(
    join(project, "node_modules/.bin/agentomatic"),
    ["config", "--targets", "opencode", "--fragments", "core-plugin", "--no-dependency", "--yes"],
    { cwd: project, env, encoding: "utf8" },
  );
  const version = JSON.parse(
    await readFile(join(project, "node_modules/@kisev/agentomatic/package.json"), "utf8"),
  ).version;
  const finalPlugins = JSON.parse(
    await readFile(join(project, ".opencode/opencode.json"), "utf8"),
  ).plugins;
  assert.deepEqual(finalPlugins, [
    pathToFileURL(join(project, "node_modules/@kisev/agentomatic/dist")).href,
    `@kisev/agentomatic@${version}`,
  ]);
  process.stdout.write("Core plugin registration pins the exact package version\n");
} finally {
  if (server && server.exitCode === null) {
    const exited = once(server, "exit");
    server.kill("SIGTERM");
    const timer = setTimeout(() => server.kill("SIGKILL"), 5000);
    await exited;
    clearTimeout(timer);
  }
  await rm(directory, { recursive: true, force: true });
}
