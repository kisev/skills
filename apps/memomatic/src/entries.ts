export type EntryAnnotations = {
  key?: string;
  status?: "active" | "superseded";
  origin?: "user" | "agent";
  observed?: string;
  project?: string;
  importance?: number;
  trigger?: string[];
  pinned?: boolean;
};

export type CorpusEntry = {
  file: string;
  line: number;
  text: string;
  annotations: EntryAnnotations;
};

const TRAILING_ANNOTATION = /\s*<!--\s*([a-z-]+):\s*([^<]*?)\s*-->\s*$/;

export function parseEntryLine(
  line: string,
): { text: string; annotations: EntryAnnotations } | null {
  let value = line.trimEnd();
  if (!value.startsWith("- ")) return null;
  const annotations: EntryAnnotations = {};
  for (let index = 0; index < 8; index += 1) {
    const match = TRAILING_ANNOTATION.exec(value);
    if (!match) break;
    const name = match[1];
    const raw = match[2];
    let consumed = true;
    if (name === "key" || name === "project" || name === "observed") {
      if (name === "observed") annotations.observed = raw;
      else if (name === "project") annotations.project = raw;
      else annotations.key = raw;
    } else if (name === "status") {
      if (raw === "active" || raw === "superseded") annotations.status = raw;
      else consumed = false;
    } else if (name === "origin") {
      if (raw === "user" || raw === "agent") annotations.origin = raw;
      else consumed = false;
    } else if (name === "importance") {
      const parsed = Number.parseInt(raw, 10);
      if (Number.isFinite(parsed) && parsed >= 1 && parsed <= 10) annotations.importance = parsed;
      else consumed = false;
    } else if (name === "trigger") {
      annotations.trigger = raw
        .split(/[;,]\s*/)
        .map((item) => item.trim())
        .filter(Boolean);
      if (!annotations.trigger.length) consumed = false;
    } else if (name === "pinned") {
      if (raw === "true") annotations.pinned = true;
      else consumed = false;
    } else consumed = false;
    if (!consumed) break;
    value = value.slice(0, match.index).trimEnd();
  }
  return { text: value, annotations };
}

export function serializeAnnotations(annotations: EntryAnnotations): string {
  const parts: string[] = [];
  if (annotations.key) parts.push(`key: ${annotations.key}`);
  if (annotations.status) parts.push(`status: ${annotations.status}`);
  if (annotations.origin) parts.push(`origin: ${annotations.origin}`);
  if (annotations.observed) parts.push(`observed: ${annotations.observed}`);
  if (annotations.project) parts.push(`project: ${annotations.project}`);
  if (annotations.importance !== undefined) parts.push(`importance: ${annotations.importance}`);
  if (annotations.trigger?.length) parts.push(`trigger: ${annotations.trigger.join("; ")}`);
  if (annotations.pinned) parts.push("pinned: true");
  return parts.map((part) => `<!-- ${part} -->`).join(" ");
}

export function entryLine(text: string, annotations: EntryAnnotations): string {
  const suffix = serializeAnnotations(annotations);
  return `- ${text}${suffix ? ` ${suffix}` : ""}`;
}

export function entryKey(entry: CorpusEntry): string | null {
  if (entry.annotations.key) return entry.annotations.key;
  return null;
}

export function entryImportance(entry: CorpusEntry): number {
  return entry.annotations.importance ?? 5;
}

export function entryObservedAt(entry: CorpusEntry): number {
  if (entry.annotations.observed) {
    const parsed = Date.parse(entry.annotations.observed);
    if (Number.isFinite(parsed)) return parsed;
  }
  return Number.NaN;
}
