import { InstallerError } from "./installer.js";

function parseKey(buffer: Buffer): { name: string; sequence: string } {
  const seq = buffer.toString();
  if (seq === "\r" || seq === "\n") return { name: "return", sequence: seq };
  if (seq === "\x03") return { name: "ctrl+c", sequence: seq };
  if (seq === "\x04") return { name: "ctrl+d", sequence: seq };
  if (seq === "\x1b" || seq === "\x1b\x1b" || seq === "\x1b\x1b\x1b")
    return { name: "escape", sequence: seq };
  if (seq === "\x1b[A" || seq === "\x1b[OA") return { name: "up", sequence: seq };
  if (seq === "\x1b[B" || seq === "\x1b[OB") return { name: "down", sequence: seq };
  if (seq === "\x1b[C" || seq === "\x1b[OC") return { name: "right", sequence: seq };
  if (seq === "\x1b[D" || seq === "\x1b[OD") return { name: "left", sequence: seq };
  return { name: "unknown", sequence: seq };
}

function clearLines(stderr: NodeJS.WriteStream, count: number): void {
  for (let i = 0; i < count; i++) {
    stderr.write("\x1b[A\x1b[K");
  }
}

export async function selectOption(
  label: string,
  options: readonly string[],
  stdin: NodeJS.ReadStream = process.stdin,
  stderr: NodeJS.WriteStream = process.stderr,
  initial = 0,
): Promise<number | null> {
  if (!stdin.isTTY || !stderr.isTTY) {
    throw new InstallerError(
      "terminal_required",
      "This operation requires an interactive terminal",
    );
  }
  let selected = Math.max(0, Math.min(initial, options.length - 1));
  const lineCount = options.length + 1; // label + options

  function render(): void {
    stderr.write(`${label}\n`);
    for (let i = 0; i < options.length; i++) {
      const cursor = i === selected ? "> " : "  ";
      stderr.write(`${cursor}${options[i]}\n`);
    }
  }

  render();

  return new Promise((resolve) => {
    stdin.setRawMode(true);
    stdin.resume();

    function cleanup(): void {
      stdin.setRawMode(false);
      stdin.pause();
      stdin.removeListener("data", onData);
    }

    function onData(data: Buffer): void {
      let remaining = data.toString();
      while (remaining) {
        const sequence = remaining.startsWith("\x1b[") ? remaining.slice(0, 3) : remaining[0];
        remaining = remaining.slice(sequence.length);
        const key = parseKey(Buffer.from(sequence));
        if (key.name === "ctrl+c" || key.name === "ctrl+d" || key.name === "escape") {
          cleanup();
          clearLines(stderr, lineCount);
          resolve(null);
          return;
        }
        if (key.name === "return") {
          cleanup();
          clearLines(stderr, lineCount);
          resolve(selected);
          return;
        }
        if (key.name === "up") {
          clearLines(stderr, lineCount);
          selected = (selected - 1 + options.length) % options.length;
          render();
        } else if (key.name === "down") {
          clearLines(stderr, lineCount);
          selected = (selected + 1) % options.length;
          render();
        }
      }
    }

    stdin.on("data", onData);
  });
}

export async function promptText(
  label: string,
  stdin: NodeJS.ReadStream = process.stdin,
  stderr: NodeJS.WriteStream = process.stderr,
): Promise<string | null> {
  if (!stdin.isTTY || !stderr.isTTY) {
    throw new InstallerError(
      "terminal_required",
      "This operation requires an interactive terminal",
    );
  }
  stderr.write(`${label} `);
  return new Promise((resolve) => {
    let buffer = "";
    stdin.setRawMode(true);
    stdin.resume();

    function cleanup(): void {
      stdin.setRawMode(false);
      stdin.pause();
      stdin.removeListener("data", onData);
    }

    function onData(data: Buffer): void {
      for (const seq of data.toString()) {
        if (seq === "\r" || seq === "\n") {
          cleanup();
          stderr.write("\n");
          resolve(buffer.trim() || null);
          return;
        }
        if (seq === "\x03" || seq === "\x04" || seq === "\x1b") {
          cleanup();
          stderr.write("\n");
          resolve(null);
          return;
        }
        if (seq === "\x7f" || seq === "\b") {
          if (buffer.length > 0) {
            buffer = buffer.slice(0, -1);
            stderr.write("\x1b[D \x1b[D");
          }
          continue;
        }
        if (seq >= " ") {
          buffer += seq;
          stderr.write(seq);
        }
      }
    }

    stdin.on("data", onData);
  });
}
