import { spawn, type ChildProcess } from "node:child_process";
import { constants as osConstants } from "node:os";

export class MutationNotAttempted extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MutationNotAttempted";
  }
}

export class MutationOutcomeUnknown extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MutationOutcomeUnknown";
  }
}

export interface MutationProcessResult {
  code: number;
  stdout: Buffer;
  stderr: Buffer;
}

export interface MutationProcessOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  outputLimit?: number;
  graceMs?: number;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function signalNumber(signal: string): number {
  const signals = osConstants.signals as unknown as Record<string, number | undefined>;
  return signals[signal] ?? 0;
}

async function waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return true;
  return new Promise((resolve) => {
    const onExit = () => {
      clearTimeout(timer);
      resolve(true);
    };
    const timer = setTimeout(() => {
      child.off("exit", onExit);
      resolve(false);
    }, timeoutMs);
    child.on("exit", onExit);
  });
}

async function terminate(child: ChildProcess, graceMs: number): Promise<void> {
  if (child.pid === undefined) return;
  const group = -child.pid;
  try {
    process.kill(group, "SIGTERM");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
  }
  const deadline = performance.now() + graceMs;
  while (performance.now() < deadline) {
    try {
      process.kill(group, 0);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ESRCH") break;
      throw error;
    }
    await delay(10);
  }
  try {
    process.kill(group, "SIGKILL");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
  }
  if (!(await waitForExit(child, 500))) {
    throw new MutationOutcomeUnknown("GitLab mutation cleanup failed; inspect the target");
  }
}

export async function runMutationProcess(
  command: string[],
  payload: Buffer,
  options: MutationProcessOptions = {},
): Promise<MutationProcessResult> {
  const timeoutMs = options.timeoutMs ?? 60_000;
  const outputLimit = options.outputLimit ?? 1024 * 1024;
  const graceMs = options.graceMs ?? 500;
  if (options.signal?.aborted) throw new MutationNotAttempted("Command cancelled before sending");
  if (process.platform === "win32") {
    throw new MutationNotAttempted("GitLab mutation requires POSIX process groups");
  }
  let child: ChildProcess;
  try {
    child = spawn(command[0], command.slice(1), {
      detached: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch {
    throw new MutationNotAttempted("GitLab mutation was not attempted; retry is safe");
  }
  const { stdin, stdout, stderr } = child;
  if (stdin === null || stdout === null || stderr === null) {
    throw new MutationOutcomeUnknown("GitLab mutation pipes are unavailable");
  }
  const deadline = performance.now() + timeoutMs;
  let cancel = (): void => {};
  const outcome = new Promise<MutationProcessResult>((resolve, reject) => {
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    let stdoutSize = 0;
    let stderrSize = 0;
    let exitCode: number | null = null;
    let exitSignal: string | null = null;
    let exited = false;
    let stdoutDone = false;
    let stderrDone = false;
    let stdinClosed = false;
    let settled = false;
    const settle = (error: Error | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error !== null) {
        reject(error);
        return;
      }
      const code =
        exitCode !== null ? exitCode : exitSignal !== null ? -signalNumber(exitSignal) : 0;
      resolve({ code, stdout: Buffer.concat(stdoutChunks), stderr: Buffer.concat(stderrChunks) });
    };
    const finishIfComplete = () => {
      if (exited && stdoutDone && stderrDone && stdinClosed) settle(null);
    };
    const timer = setTimeout(
      () => settle(new MutationOutcomeUnknown("GitLab mutation timed out; inspect the target")),
      Math.max(0, deadline - performance.now()),
    );
    cancel = () =>
      settle(new MutationOutcomeUnknown("Local waiting cancelled; check GitLab before repeating"));
    options.signal?.addEventListener("abort", cancel, { once: true });
    if (options.signal?.aborted) cancel();
    stdout.on("data", (chunk: Buffer) => {
      stdoutChunks.push(chunk);
      stdoutSize += chunk.length;
      if (stdoutSize > outputLimit) {
        settle(
          new MutationOutcomeUnknown(
            "GitLab mutation output exceeds the size limit; inspect the target",
          ),
        );
      }
    });
    stdout.on("end", () => {
      stdoutDone = true;
      finishIfComplete();
    });
    stdout.on("error", (error: NodeJS.ErrnoException) => {
      settle(new MutationOutcomeUnknown(error.message));
    });
    stderr.on("data", (chunk: Buffer) => {
      stderrChunks.push(chunk);
      stderrSize += chunk.length;
      if (stderrSize > outputLimit) {
        settle(
          new MutationOutcomeUnknown(
            "GitLab mutation output exceeds the size limit; inspect the target",
          ),
        );
      }
    });
    stderr.on("end", () => {
      stderrDone = true;
      finishIfComplete();
    });
    stderr.on("error", (error: NodeJS.ErrnoException) => {
      settle(new MutationOutcomeUnknown(error.message));
    });
    stdin.on("error", (error: NodeJS.ErrnoException) => {
      if (error.code === "EPIPE") {
        stdinClosed = true;
        finishIfComplete();
      } else {
        settle(new MutationOutcomeUnknown(error.message));
      }
    });
    stdin.on("close", () => {
      stdinClosed = true;
      finishIfComplete();
    });
    child.on("error", () => {
      settle(new MutationNotAttempted("GitLab mutation was not attempted; retry is safe"));
    });
    child.on("exit", (code, signal) => {
      exited = true;
      exitCode = code;
      exitSignal = signal;
      finishIfComplete();
    });
    stdin.end(payload);
  });
  try {
    return await outcome;
  } finally {
    options.signal?.removeEventListener("abort", cancel);
    await terminate(child, graceMs);
  }
}
