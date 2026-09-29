import { Command, Option, CommanderError, InvalidArgumentError } from "commander";
import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
export { Command, Option, CommanderError, InvalidArgumentError };

export function integer(value: string): number {
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)))
    throw new InvalidArgumentError("expected a non-negative integer");
  return Number(value);
}
export function duration(value: string): number {
  const match = /^(\d+)(ms|s|m|h)?$/.exec(value);
  if (!match) throw new InvalidArgumentError("expected a duration such as 500ms, 30s or 5m");
  const result =
    Number(match[1]) * ({ ms: 1, s: 1000, m: 60000, h: 3600000 }[match[2] ?? "ms"] ?? 1);
  if (!Number.isSafeInteger(result) || result < 0)
    throw new InvalidArgumentError("duration is out of range");
  return result;
}
export function program(name: string, description: string, version: string): Command {
  return new Command(name)
    .description(description)
    .version(version)
    .exitOverride()
    .configureHelp({ showGlobalOptions: true })
    .showHelpAfterError()
    .configureOutput({ outputError: () => {} });
}
export function common(command: Command, prefix: string): Command {
  return command
    .addOption(
      new Option("--config <file>", "JSON configuration file (CLI > env > file > defaults)").env(
        `${prefix}_CONFIG`,
      ),
    )
    .addOption(new Option("--json", "machine-readable result on stdout").env(`${prefix}_JSON`))
    .addOption(
      new Option("--log-level <level>", "diagnostic verbosity on stderr")
        .choices(["debug", "info", "warn", "error", "silent"])
        .env(`${prefix}_LOG_LEVEL`),
    )
    .addOption(
      new Option("--log-format <format>", "diagnostic format on stderr")
        .choices(["text", "json"])
        .env(`${prefix}_LOG_FORMAT`),
    )
    .addOption(
      new Option("--progress <mode>", "terminal progress; never written to stdout")
        .choices(["auto", "always", "never"])
        .env(`${prefix}_PROGRESS`),
    )
    .addOption(
      new Option("--color <mode>", "color policy (NO_COLOR disables color)")
        .choices(["auto", "always", "never"])
        .env(`${prefix}_COLOR`),
    );
}
export async function configFile(path: string | undefined): Promise<Record<string, unknown>> {
  if (!path) return {};
  const value: unknown = JSON.parse(await readFile(path, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new InvalidArgumentError("configuration must be a JSON object");
  return value as Record<string, unknown>;
}
export function configFileSync(path: string | undefined): Record<string, unknown> {
  if (!path) return {};
  const value: unknown = JSON.parse(readFileSync(path, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new InvalidArgumentError("configuration must be a JSON object");
  return value as Record<string, unknown>;
}
export function applyConfig(command: Command, config: Record<string, unknown>): void {
  for (const option of command.options) {
    const key = option.attributeName();
    if (!(key in config) || ["cli", "env"].includes(command.getOptionValueSource(key) ?? ""))
      continue;
    if (["yes", "config"].includes(key)) continue;
    const value = config[key];
    if (option.required || option.optional) {
      const raw = String(value);
      if (option.argChoices && !option.argChoices.includes(raw))
        throw new InvalidArgumentError(`invalid configuration value for ${key}`);
      command.setOptionValueWithSource(
        key,
        option.parseArg ? option.parseArg(raw, undefined) : raw,
        "config",
      );
    } else {
      if (typeof value !== "boolean") throw new InvalidArgumentError(`${key} must be boolean`);
      command.setOptionValueWithSource(key, value, "config");
    }
  }
}
export type Event = {
  phase: string;
  message: string;
  level?: "debug" | "info" | "warn" | "error";
  completed?: number;
  total?: number;
  elapsedMs?: number;
  [key: string]: unknown;
};
export type Observe = (event: Event) => void;
export function reporter(options: Record<string, unknown> = {}): {
  emit: Observe;
  close: () => void;
} {
  const started = Date.now();
  const level = String(options.logLevel ?? "info");
  const levels = ["debug", "info", "warn", "error", "silent"];
  const json = options.logFormat === "json";
  const interactive =
    !json &&
    options.progress !== "never" &&
    (options.progress === "always" || process.stderr.isTTY);
  let current: Event | undefined;
  let painted = false;
  let frame = 0;
  let meter: { phase: string; completed: number; total: number } | undefined;
  const bar = () => {
    if (!meter || meter.total <= 0) return "";
    const ratio = Math.min(1, Math.max(0, meter.completed / meter.total));
    const filled = Math.floor(ratio * 16);
    return ` | ${meter.phase} [${"█".repeat(filled)}${"░".repeat(16 - filled)}] ${Math.floor(ratio * 100)}%`;
  };
  const clean = (text: string) =>
    Array.from(text, (char) => {
      const code = char.codePointAt(0)!;
      return code < 32 || (code >= 127 && code <= 159) ? " " : char;
    }).join("");
  const line = (event: Event) =>
    `${event.phase}: ${event.message}${event.total !== undefined ? ` [${event.completed ?? 0}/${event.total}]` : ""} (${Math.floor((Date.now() - started) / 1000)}s)`;
  const clear = () => {
    if (painted) {
      process.stderr.write("\r\x1b[2K");
      painted = false;
    }
  };
  const timer =
    interactive && level !== "silent"
      ? setInterval(() => {
          if (current) {
            const color =
              process.env.NO_COLOR === undefined &&
              (options.color === "always" || (options.color !== "never" && process.stderr.isTTY));
            process.stderr.write(
              `\r\x1b[2K${color ? "\x1b[36m" : ""}${["⠋", "⠙", "⠹", "⠸"][frame++ % 4]} ${clean(line(current))}${bar()}${color ? "\x1b[0m" : ""}`,
            );
            painted = true;
          }
        }, 120)
      : undefined;
  timer?.unref();
  const emit: Observe = (event) => {
    const severity = event.level ?? "info";
    if (levels.indexOf(severity) < levels.indexOf(level)) return;
    current = event;
    if (event.total !== undefined)
      meter =
        event.total > 0
          ? {
              phase: event.phase.split(".")[0],
              completed: event.completed ?? 0,
              total: event.total,
            }
          : undefined;
    else if (meter && meter.completed >= meter.total) meter = undefined;
    clear();
    process.stderr.write(
      json
        ? `${JSON.stringify({ at: new Date().toISOString(), elapsedMs: Date.now() - started, ...event })}\n`
        : `${clean(line(event))}\n`,
    );
  };
  return {
    emit,
    close: () => {
      if (timer) clearInterval(timer);
      clear();
    },
  };
}
export function cancellation(): { signal: AbortSignal; dispose: () => void } {
  const controller = new AbortController();
  const interrupt = () => controller.abort(new Error("interrupted"));
  process.on("SIGINT", interrupt);
  process.on("SIGTERM", interrupt);
  process.on("SIGHUP", interrupt);
  return {
    signal: controller.signal,
    dispose: () => {
      process.off("SIGINT", interrupt);
      process.off("SIGTERM", interrupt);
      process.off("SIGHUP", interrupt);
    },
  };
}
export function fail(name: string, error: unknown, json = false): void {
  if (error instanceof CommanderError && error.exitCode === 0) return;
  const message = error instanceof Error ? error.message : String(error);
  const interrupted = /interrupted|aborted/i.test(message);
  process.stderr.write(
    json ? `${JSON.stringify({ status: "error", message })}\n` : `${name}: ${message}\n`,
  );
  process.exitCode = /timeout|timed out|deadline/i.test(message)
    ? 124
    : interrupted
      ? 130
      : error instanceof CommanderError
        ? 2
        : 1;
}
