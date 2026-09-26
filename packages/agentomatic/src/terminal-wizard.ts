import { InstallerError } from "./installer.js";

function parseKey(buffer: Buffer): { name: string; sequence: string } {
  const seq = buffer.toString();
  if (seq === "\r" || seq === "\n") return { name: "return", sequence: seq };
  if (seq === " ") return { name: "space", sequence: seq };
  if (seq === "a" || seq === "A") return { name: "all", sequence: seq };
  if (seq === "n" || seq === "N") return { name: "none", sequence: seq };
  if (seq === "\x03") return { name: "ctrl+c", sequence: seq };
  if (seq === "\x04") return { name: "ctrl+d", sequence: seq };
  if (seq === "\x1b" || seq === "\x1b\x1b" || seq === "\x1b\x1b\x1b")
    return { name: "escape", sequence: seq };
  if (seq === "\x1b[A" || seq === "\x1bOA" || seq === "\x1b[OA")
    return { name: "up", sequence: seq };
  if (seq === "\x1b[B" || seq === "\x1bOB" || seq === "\x1b[OB")
    return { name: "down", sequence: seq };
  if (seq === "\x1b[C" || seq === "\x1bOC" || seq === "\x1b[OC")
    return { name: "right", sequence: seq };
  if (seq === "\x1b[D" || seq === "\x1bOD" || seq === "\x1b[OD")
    return { name: "left", sequence: seq };
  return { name: "unknown", sequence: seq };
}

function nextSequence(remaining: string): string {
  if (remaining.startsWith("\x1b[O")) return remaining.slice(0, 4);
  if (remaining.startsWith("\x1b[") || remaining.startsWith("\x1bO")) return remaining.slice(0, 3);
  return remaining[0];
}

function validateOptions(options: readonly string[]): void {
  if (options.length === 0)
    throw new InstallerError("invalid_input", "Interactive selector requires at least one option");
  if (new Set(options).size !== options.length)
    throw new InstallerError("invalid_input", "Interactive selector options must be unique");
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
  validateOptions(options);
  let selected = Math.max(0, Math.min(initial, options.length - 1));
  const lineCount = options.length + 2;

  function render(): void {
    stderr.write(`? ${label}\n`);
    stderr.write("  Up/Down move | Enter select | Esc cancel\n");
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
        const sequence = nextSequence(remaining);
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

export async function selectOptions(
  label: string,
  options: readonly string[],
  initialSelected: readonly string[] = [],
  stdin: NodeJS.ReadStream = process.stdin,
  stderr: NodeJS.WriteStream = process.stderr,
): Promise<string[] | null> {
  if (!stdin.isTTY || !stderr.isTTY) {
    throw new InstallerError(
      "terminal_required",
      "This operation requires an interactive terminal",
    );
  }
  validateOptions(options);
  const allowed = new Set(options);
  for (const value of initialSelected) {
    if (!allowed.has(value))
      throw new InstallerError("invalid_input", `Unknown initial selector option: ${value}`);
  }
  const selected = new Set(initialSelected);
  let active = 0;
  const lineCount = options.length + 3;

  function render(): void {
    stderr.write(`? ${label}\n`);
    stderr.write("  Up/Down move | Space toggle | A all | N none | Enter confirm | Esc cancel\n");
    for (let index = 0; index < options.length; index += 1) {
      const cursor = index === active ? "> " : "  ";
      const marker = selected.has(options[index]) ? "[x]" : "[ ]";
      stderr.write(`${cursor}${marker} ${options[index]}\n`);
    }
    stderr.write(`  Selected ${selected.size}/${options.length}\n`);
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

    function finish(value: string[] | null): void {
      cleanup();
      clearLines(stderr, lineCount);
      resolve(value);
    }

    function redraw(update: () => void): void {
      clearLines(stderr, lineCount);
      update();
      render();
    }

    function onData(data: Buffer): void {
      let remaining = data.toString();
      while (remaining) {
        const sequence = nextSequence(remaining);
        remaining = remaining.slice(sequence.length);
        const key = parseKey(Buffer.from(sequence));
        if (key.name === "ctrl+c" || key.name === "ctrl+d" || key.name === "escape") {
          finish(null);
          return;
        }
        if (key.name === "return") {
          finish(options.filter((option) => selected.has(option)));
          return;
        }
        if (key.name === "up") {
          redraw(() => {
            active = (active - 1 + options.length) % options.length;
          });
        } else if (key.name === "down") {
          redraw(() => {
            active = (active + 1) % options.length;
          });
        } else if (key.name === "space") {
          redraw(() => {
            const option = options[active];
            if (selected.has(option)) selected.delete(option);
            else selected.add(option);
          });
        } else if (key.name === "all") {
          redraw(() => {
            for (const option of options) selected.add(option);
          });
        } else if (key.name === "none") {
          redraw(() => selected.clear());
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
  stderr.write(`? ${label}\n`);
  stderr.write("  Type a value | Enter confirm | Esc cancel\n");
  stderr.write("> ");
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
