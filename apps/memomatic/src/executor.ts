import { spawn } from "node:child_process";

export type ModelExecutor = {
  name: string;
  complete(request: { system: string; prompt: string }): Promise<string>;
};

export function extractJson(response: string): unknown {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(response);
  const candidates = [fenced?.[1], response].filter(Boolean) as string[];
  for (const candidate of candidates) {
    const start = candidate.indexOf("{");
    const end = candidate.lastIndexOf("}");
    if (start === -1 || end <= start) continue;
    try {
      return JSON.parse(candidate.slice(start, end + 1));
    } catch {
      continue;
    }
  }
  throw new Error("model response contains no JSON object");
}

export class OpenCodeExecutor implements ModelExecutor {
  readonly name = "opencode";

  constructor(
    private readonly options: {
      model: string | null;
      variant: string | null;
      binary?: string;
    },
  ) {}

  async complete(request: { system: string; prompt: string }): Promise<string> {
    const args = ["run", "--agent", "build", "--format", "json"];
    if (this.options.model) args.push("--model", this.options.model);
    if (this.options.variant) args.push("--variant", this.options.variant);
    args.push("--", `[memomatic-internal] ${request.system}\n\n${request.prompt}`);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const output = await this.spawnOnce(args);
      try {
        const texts: string[] = [];
        for (const line of output.split("\n")) {
          if (!line.trim()) continue;
          const event = JSON.parse(line) as {
            type?: string;
            part?: { text?: string };
          };
          if (event.type === "error") throw new Error("opencode returned an error event");
          if (event.type === "text" && typeof event.part?.text === "string")
            texts.push(event.part.text);
        }
        const parsed = extractJson(texts.join("\n"));
        return JSON.stringify(parsed);
      } catch {
        if (attempt === 1) throw new Error("opencode run returned no parsable JSON twice");
      }
    }
    throw new Error("unreachable");
  }

  private spawnOnce(args: string[]): Promise<string> {
    return new Promise((resolve, reject) => {
      const child = spawn(this.options.binary ?? "opencode", args, {
        env: process.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (chunk: Buffer) => {
        stdout += chunk.toString("utf8");
      });
      child.stderr.on("data", (chunk: Buffer) => {
        stderr += chunk.toString("utf8");
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) resolve(stdout);
        else reject(new Error(`opencode run exited ${code}: ${stderr.slice(0, 400)}`));
      });
    });
  }
}
