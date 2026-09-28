import { readFile, readdir, unlink } from "node:fs/promises";
import { join } from "node:path";
import { assertSafePath, writeAtomic } from "@kisev/safe-fs";
import { STATUSES, type Card, type Snapshot, type Store } from "./store.js";

export function cardFilename(card: Card): string {
  const slug =
    card.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 40)
      .replace(/-$/, "") || "card";
  return `${card.id}-${slug}.md`;
}
export function cardMarkdown(card: Card): string {
  const { activity, claim_state, claim_remaining_seconds: _remaining, ...fields } = card;
  if (claim_state !== "held") {
    fields.claimed_by = null;
    fields.claim_expires_at = null;
  }
  return [
    "---",
    ...Object.entries(fields).map(([key, value]) => `${key}: ${JSON.stringify(value)}`),
    "---",
    "",
    `# ${card.title}`,
    "",
    card.notes.trim() || "_No notes._",
    "",
    "## Activity",
    "",
    ...activity
      .slice()
      .reverse()
      .map(
        (event) =>
          `- ${event.at} \`${event.kind}\` by ${event.actor}${event.detail ? ` — ${event.detail}` : ""}`,
      ),
    "",
  ].join("\n");
}
export async function renderPage(snapshot: Snapshot): Promise<string> {
  const template = await readFile(new URL("../assets/viewer.html", import.meta.url), "utf8");
  return template.replace(
    "__TASKMATIC_SNAPSHOT_JSON__",
    JSON.stringify(snapshot).replace(/</g, "\\u003c"),
  );
}
export async function exportAll(store: Store): Promise<void> {
  const snapshot = store.snapshot();
  const root = join(store.root, "export");
  const wanted = new Set<string>();
  const write = async (path: string, content: string) => {
    wanted.add(path);
    await writeAtomic(path, Buffer.from(content), 0o600);
  };
  for (const board of snapshot.boards) {
    const cards = snapshot.cards.filter((card) => card.board === board.slug);
    const directory = join(root, "boards", board.slug);
    const lines = [
      `# Board ${board.title}`,
      "",
      `_Slug \`${board.slug}\`. Generated ${snapshot.generated_at}. ${cards.length} cards._`,
      "",
    ];
    for (const status of STATUSES) {
      lines.push(`## ${status[0].toUpperCase()}${status.slice(1)}`, "");
      const selected = cards.filter((card) => card.status === status);
      lines.push(
        ...selected.map(
          (card) =>
            `- \`${card.id}\` [${card.title}](cards/${cardFilename(card)}) (${card.priority}${card.assignee ? `; assignee: ${card.assignee}` : ""}${card.claim_state ? `; claim ${card.claim_state}: ${card.claimed_by}` : ""})`,
        ),
      );
      if (!selected.length) lines.push("_None._");
      lines.push("");
    }
    await write(join(directory, "BOARD.md"), lines.join("\n"));
    for (const card of cards)
      await write(join(directory, "cards", cardFilename(card)), cardMarkdown(card));
  }
  const removeStale = async (path: string): Promise<void> => {
    await assertSafePath(path, { target: "directory" });
    for (const item of await readdir(path, { withFileTypes: true }).catch(
      (error: NodeJS.ErrnoException) => {
        if (error.code === "ENOENT") return [];
        throw error;
      },
    )) {
      const file = join(path, item.name);
      if (item.isSymbolicLink()) throw new Error("symlink in taskmatic export");
      if (item.isDirectory()) await removeStale(file);
      else if (item.isFile() && file.endsWith(".md") && !wanted.has(file)) await unlink(file);
    }
  };
  await removeStale(join(root, "boards"));
  await write(join(root, "web/snapshot.json"), `${JSON.stringify(snapshot, null, 2)}\n`);
  await write(join(root, "web/index.html"), await renderPage(snapshot));
}
