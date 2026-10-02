import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { backendTests } from "./test-selection.mjs";

const directory = new URL("../test/", import.meta.url);
const files = backendTests(readdirSync(directory, { recursive: true })).map((name) =>
  join(fileURLToPath(directory), name),
);
if (!files.length) throw new Error("No reviewmatic backend tests found");
const result = spawnSync(process.execPath, ["--test", ...files], { stdio: "inherit" });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
