import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import type { OperationOptions } from "./operations.js";

export type ModelExecutor = {
  name: string;
  complete(request: { system: string; prompt: string }): Promise<string>;
  close?: () => Promise<void>;
};
export function extractJson(response: string): unknown {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(response);
  for (const candidate of [fenced?.[1], response]) {
    if (!candidate) continue;
    const start = candidate.indexOf("{");
    const end = candidate.lastIndexOf("}");
    if (start < 0 || end <= start) continue;
    try {
      return JSON.parse(candidate.slice(start, end + 1));
    } catch {
      continue;
    }
  }
  throw new Error("model response contains no JSON object");
}
type ExecutorOptions = OperationOptions & {
  model: string | null;
  variant: string | null;
  binary?: string;
  url?: string | null;
  timeoutMs?: number;
  retries?: number;
};
export class OpenCodeExecutor implements ModelExecutor {
  readonly name = "opencode";
  readonly usage = {
    calls: 0,
    retries: 0,
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    usageAvailable: false,
    charactersSent: 0,
  };
  private child?: ChildProcess;
  private directory?: string;
  private url?: string;
  private authorization?: string;
  constructor(private readonly options: ExecutorOptions) {}
  private async initialize(): Promise<void> {
    if (this.url) return;
    if (this.options.url) {
      const url = new URL(this.options.url);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
        throw new Error("invalid OpenCode URL");
      this.url = url.href.replace(/\/$/, "");
      if (process.env.OPENCODE_SERVER_PASSWORD)
        this.authorization = `Basic ${Buffer.from(`${process.env.OPENCODE_SERVER_USERNAME ?? "opencode"}:${process.env.OPENCODE_SERVER_PASSWORD}`).toString("base64")}`;
      return;
    }
    let inherited: Record<string, unknown> = {};
    if (process.env.OPENCODE_CONFIG_CONTENT) {
      try {
        const value: unknown = JSON.parse(process.env.OPENCODE_CONFIG_CONTENT);
        if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
        inherited = value as Record<string, unknown>;
      } catch {
        throw new Error("OpenCode inline configuration must be a JSON object");
      }
    }
    this.directory = await mkdtemp(join(tmpdir(), "memomatic-opencode-"));
    const password = randomBytes(24).toString("hex");
    this.authorization = `Basic ${Buffer.from(`opencode:${password}`).toString("base64")}`;
    this.options.observe?.({
      phase: "opencode.start",
      message: "Starting one isolated OpenCode server for this run",
    });
    const child = spawn(
      this.options.binary ?? "opencode",
      ["serve", "--hostname", "127.0.0.1", "--port", "0", "--pure"],
      {
        cwd: this.directory,
        detached: process.platform !== "win32",
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          OPENCODE_SERVER_USERNAME: "opencode",
          OPENCODE_SERVER_PASSWORD: password,
          OPENCODE_DISABLE_PROJECT_CONFIG: "1",
          OPENCODE_DISABLE_EXTERNAL_SKILLS: "1",
          OPENCODE_DISABLE_CLAUDE_CODE_SKILLS: "1",
          OPENCODE_DISABLE_DEFAULT_PLUGINS: "1",
          OPENCODE_CONFIG_CONTENT: JSON.stringify({
            ...inherited,
            permission: "deny",
            tools: { "*": false },
            agent: {
              ...(inherited.agent as Record<string, unknown> | undefined),
              memomatic: {
                mode: "primary",
                description: "Bounded memory extraction",
                prompt: "Return only the requested JSON. Do not use tools.",
                permission: "deny",
                tools: { "*": false },
              },
            },
          }),
        },
      },
    );
    this.child = child;
    this.url = await new Promise<string>((resolve, reject) => {
      let output = "";
      const timeout = setTimeout(() => done(new Error("OpenCode startup timed out")), 30000);
      const abort = () =>
        done(
          this.options.signal?.reason instanceof Error
            ? this.options.signal.reason
            : new Error("interrupted"),
        );
      const failed = (error: Error) => done(error);
      const closed = () => done(new Error("OpenCode exited before becoming ready"));
      const data = (chunk: Buffer) => {
        output = (output + chunk.toString()).slice(-8192);
        const match = /https?:\/\/127\.0\.0\.1:\d+/.exec(output);
        if (match) done(undefined, match[0]);
      };
      const done = (error?: Error, url?: string) => {
        clearTimeout(timeout);
        child.stdout?.off("data", data);
        child.stderr?.off("data", data);
        child.off("error", failed);
        child.off("exit", closed);
        this.options.signal?.removeEventListener("abort", abort);
        if (error) reject(error);
        else resolve(url!);
      };
      child.stdout?.on("data", data);
      child.stderr?.on("data", data);
      child.once("error", failed);
      child.once("exit", closed);
      this.options.signal?.addEventListener("abort", abort, { once: true });
      if (this.options.signal?.aborted) abort();
    });
    // Drain logs without retaining provider output, credentials or prompts.
    child.stdout?.resume();
    child.stderr?.resume();
    this.options.observe?.({ phase: "opencode.ready", message: "OpenCode server ready" });
  }
  private async request(
    path: string,
    body: unknown,
    signal: AbortSignal,
  ): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.url}${path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(this.authorization ? { authorization: this.authorization } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });
    if (!response.ok)
      throw new Error(
        `OpenCode ${path.includes("message") ? "model request" : "session request"} failed: HTTP ${response.status}`,
      );
    return (await response.json()) as Record<string, unknown>;
  }
  async complete(request: { system: string; prompt: string }): Promise<string> {
    this.options.signal?.throwIfAborted();
    await this.initialize();
    for (let attempt = 0; attempt <= (this.options.retries ?? 1); attempt++) {
      this.options.signal?.throwIfAborted();
      const signal = AbortSignal.any([
        AbortSignal.timeout(this.options.timeoutMs ?? 180000),
        ...(this.options.signal ? [this.options.signal] : []),
      ]);
      let id: string | undefined;
      const started = Date.now();
      const heartbeat = setInterval(
        () =>
          this.options.observe?.({
            phase: "model.wait",
            message: "Waiting for OpenCode/model response",
            elapsedMs: Date.now() - started,
            attempt: attempt + 1,
          }),
        15000,
      );
      heartbeat.unref();
      try {
        const session = await this.request(
          "/session",
          {
            title: "[memomatic-internal] memory extraction",
            permission: [{ permission: "*", pattern: "*", action: "deny" }],
          },
          signal,
        );
        if (typeof session.id !== "string")
          throw new Error("OpenCode session response is malformed");
        id = session.id;
        const slash = this.options.model?.indexOf("/") ?? -1;
        if (this.options.model && slash < 1)
          throw new Error("model must use provider/model format");
        this.usage.calls++;
        this.usage.charactersSent += request.system.length + request.prompt.length;
        this.options.observe?.({
          phase: "model.request",
          message: "Sending prepared fragment to OpenCode",
          characters: request.prompt.length,
          attempt: attempt + 1,
        });
        const response = await this.request(
          `/session/${encodeURIComponent(id)}/message`,
          {
            agent: this.options.url ? "build" : "memomatic",
            system: request.system,
            tools: { "*": false },
            ...(this.options.model
              ? {
                  model: {
                    providerID: this.options.model.slice(0, slash),
                    modelID: this.options.model.slice(slash + 1),
                  },
                }
              : {}),
            ...(this.options.variant ? { variant: this.options.variant } : {}),
            parts: [{ type: "text", text: `[memomatic-internal] ${request.prompt}` }],
          },
          signal,
        );
        const info = response.info as
          | {
              error?: unknown;
              tokens?: {
                input?: number;
                output?: number;
                cache?: { read?: number; write?: number };
              };
            }
          | undefined;
        if (info?.error)
          throw new Error("OpenCode model returned an error; inspect the configured provider");
        if (info?.tokens) {
          this.usage.usageAvailable = true;
          this.usage.inputTokens += info.tokens.input ?? 0;
          this.usage.outputTokens += info.tokens.output ?? 0;
          this.usage.cacheReadTokens += info.tokens.cache?.read ?? 0;
          this.usage.cacheWriteTokens += info.tokens.cache?.write ?? 0;
        }
        const parts = response.parts as Array<{ type?: string; text?: string }> | undefined;
        if (!Array.isArray(parts)) throw new Error("OpenCode model response is malformed");
        const parsed = extractJson(
          parts
            .filter((part) => part.type === "text")
            .map((part) => part.text ?? "")
            .join("\n"),
        );
        this.options.observe?.({
          phase: "model.done",
          message: "Model response received",
          elapsedMs: Date.now() - started,
          ...this.usage,
        });
        return JSON.stringify(parsed);
      } catch (error) {
        if (id)
          await this.request(
            `/session/${encodeURIComponent(id)}/abort`,
            {},
            AbortSignal.timeout(3000),
          ).catch(() => undefined);
        if (this.options.signal?.aborted) throw this.options.signal.reason;
        if (attempt === (this.options.retries ?? 1))
          throw new Error(
            `OpenCode request failed after ${attempt + 1} attempt(s): ${(error as Error).message}`,
          );
        this.usage.retries++;
        this.options.observe?.({
          phase: "model.retry",
          message: "Retrying failed model request",
          level: "warn",
          attempt: attempt + 2,
          reason: (error as Error).message,
        });
      } finally {
        clearInterval(heartbeat);
      }
    }
    throw new Error("unreachable");
  }
  async close(): Promise<void> {
    const child = this.child;
    if (child?.pid && child.exitCode === null && child.signalCode === null) {
      await new Promise<void>((resolve) => {
        const kill = (signal: NodeJS.Signals) => {
          try {
            if (process.platform !== "win32" && child.pid) process.kill(-child.pid, signal);
            else child.kill(signal);
          } catch {}
        };
        const timer = setTimeout(() => kill("SIGKILL"), 1000);
        timer.unref();
        child.once("close", () => {
          clearTimeout(timer);
          resolve();
        });
        kill("SIGTERM");
      });
    }
    if (child?.pid && process.platform !== "win32") {
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch {}
    }
    this.child = undefined;
    if (this.directory) await rm(this.directory, { recursive: true, force: true });
  }
}
