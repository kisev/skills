import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

export type EmbeddingSettings = {
  url: string;
  model: string;
  /** Explicit query instruction; null keeps the built-in Qwen3 auto-detection. */
  queryInstruction: string | null;
  documentPrefix: string;
  queryPrefix: string;
  bearerEnv: string | null;
  timeoutMs: number;
  maxBatchTexts: number;
  maxTextChars: number;
};

export type RerankerSettings = {
  url: string;
  model: string;
  bearerEnv: string | null;
  timeoutMs: number;
  candidates: number;
  minScore: number;
  maxDocuments: number;
  maxChars: number;
};

export type MemomaticSettings = {
  embedding: EmbeddingSettings | null;
  reranker: RerankerSettings | null;
  sessions: {
    model: string | null;
    variant: string | null;
    timeoutMs: number;
    maxDurationMs: number;
    maxSessions: number;
    maxChars: number;
    retries: number;
    idleMs: number;
    opencodeUrl: string | null;
  };
  dream: {
    model: string | null;
    variant: string | null;
    minScore: number;
    minUseful: number;
    minUniqueQueries: number;
    maxCandidates: number;
    memoryBudgetLines: number;
    maxPriorEntryLoss: number;
    timeoutMs: number;
    maxDurationMs: number;
    retries: number;
  };
  search: { maxResults: number; minScore: number; minSemanticScore: number; halfLifeDays: number };
  archive: { enabled: boolean; days: number };
};

// Conservative character proxy for an input budget of roughly 4096 tokens:
// dense scripts need about two characters per token, so 8000 characters stay
// inside the example budget without claiming exact tokenization. Long texts
// are split at chunkText instead of measured with a tokenizer.
export const DEFAULT_MAX_TEXT_CHARS = 8000;
// Headroom for the server-side rerank template wrapped around query and document.
export const RERANKER_TEMPLATE_ALLOWANCE_CHARS = 1024;

export const defaultEmbedding = (url: string, model: string): EmbeddingSettings => ({
  url,
  model,
  queryInstruction: null,
  documentPrefix: "",
  queryPrefix: "",
  bearerEnv: null,
  timeoutMs: 30_000,
  maxBatchTexts: 32,
  maxTextChars: DEFAULT_MAX_TEXT_CHARS,
});

export const defaultReranker = (url: string, model: string): RerankerSettings => ({
  url,
  model,
  bearerEnv: null,
  timeoutMs: 30_000,
  candidates: 64,
  minScore: 0,
  maxDocuments: 64,
  maxChars: DEFAULT_MAX_TEXT_CHARS,
});

export const defaultSettings = (): MemomaticSettings => ({
  embedding: null,
  reranker: null,
  sessions: {
    model: null,
    variant: null,
    timeoutMs: 180000,
    maxDurationMs: 0,
    maxSessions: 0,
    maxChars: 24000,
    retries: 1,
    idleMs: 600000,
    opencodeUrl: null,
  },
  dream: {
    model: null,
    variant: null,
    minScore: 0.45,
    minUseful: 2,
    minUniqueQueries: 2,
    maxCandidates: 12,
    memoryBudgetLines: 80,
    maxPriorEntryLoss: 0.25,
    timeoutMs: 180000,
    maxDurationMs: 0,
    retries: 1,
  },
  search: { maxResults: 6, minScore: 0.35, minSemanticScore: 0.45, halfLifeDays: 30 },
  archive: { enabled: false, days: 60 },
});

function mergeSection<T extends Record<string, unknown>>(
  base: T,
  override: Record<string, unknown> | undefined,
): T {
  if (!override || typeof override !== "object") return base;
  const merged: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (key in base && value !== null && value !== undefined) merged[key] = value;
  }
  return merged as T;
}

const SESSIONS_KEYS = [
  "model",
  "variant",
  "timeoutMs",
  "maxDurationMs",
  "maxSessions",
  "maxChars",
  "retries",
  "idleMs",
  "opencodeUrl",
] as const;

function httpUrl(value: unknown, section: string): string {
  if (typeof value !== "string") throw new Error(`${section}.url must be a string`);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${section}.url must be an absolute http(s) URL`);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:")
    throw new Error(`${section}.url must use http or https`);
  return value;
}

function bearerEnvName(value: unknown, section: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(value))
    throw new Error(`${section}.bearerEnv must name an environment variable`);
  return value;
}

function boundedInt(
  value: unknown,
  section: string,
  key: string,
  min: number,
  max: number,
): number {
  if (!Number.isSafeInteger(value) || (value as number) < min || (value as number) > max)
    throw new Error(`invalid ${section}.${key}; expected an integer between ${min} and ${max}`);
  return value as number;
}

function optionalText(value: unknown, section: string, key: string): string {
  if (typeof value !== "string") throw new Error(`${section}.${key} must be a string`);
  return value;
}

function serviceEndpoint(
  raw: Record<string, unknown> | null | undefined,
  section: string,
  defaults: (url: string, model: string) => Record<string, unknown>,
  validate: (merged: Record<string, unknown>) => void,
): Record<string, unknown> | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== "object") throw new Error(`invalid ${section} settings`);
  const url = httpUrl(raw.url, section);
  if (typeof raw.model !== "string" || !raw.model.trim())
    throw new Error(`${section}.model must be a non-empty string`);
  const merged = defaults(url, raw.model);
  for (const [key, value] of Object.entries(raw)) {
    if (key in merged && value !== null && value !== undefined) merged[key] = value;
  }
  validate(merged);
  return merged;
}

export function normalizeSettings(raw: unknown): MemomaticSettings {
  const defaults = defaultSettings();
  const source = (raw ?? {}) as Record<string, unknown>;
  const search = mergeSection(
    defaults.search,
    source.search as Record<string, unknown> | undefined,
  );
  const dream = mergeSection(defaults.dream, source.dream as Record<string, unknown> | undefined);
  // Legacy single-model configs put extraction knobs under `dream`; adopt them
  // for `sessions` unless the new section overrides the key.
  const migrated: Record<string, unknown> = {
    ...((source.sessions as Record<string, unknown> | undefined) ?? {}),
  };
  const legacyDream = (source.dream as Record<string, unknown> | undefined) ?? {};
  for (const key of SESSIONS_KEYS)
    if (migrated[key] === undefined && legacyDream[key] !== undefined)
      migrated[key] = legacyDream[key];
  const sessions = mergeSection(defaults.sessions, migrated);
  for (const key of [
    "timeoutMs",
    "maxDurationMs",
    "maxSessions",
    "maxChars",
    "retries",
    "idleMs",
  ] as const)
    if (!Number.isSafeInteger(sessions[key]) || sessions[key] < 0)
      throw new Error(`invalid sessions.${key}`);
  for (const key of ["timeoutMs", "maxDurationMs", "retries"] as const)
    if (!Number.isSafeInteger(dream[key]) || dream[key] < 0)
      throw new Error(`invalid dream.${key}`);
  if (
    sessions.timeoutMs < 1 ||
    sessions.maxChars < 256 ||
    sessions.maxChars > 200000 ||
    sessions.retries > 5
  )
    throw new Error("invalid sessions request limits");
  if (dream.timeoutMs < 1 || dream.retries > 5) throw new Error("invalid dream request limits");
  for (const [section, value] of [
    ["sessions", sessions],
    ["dream", dream],
  ] as const)
    if (
      value.model !== null &&
      (typeof value.model !== "string" || !/^[^/]+\/.+/.test(value.model))
    )
      throw new Error(`${section}.model must use provider/model format`);
  if (sessions.variant !== null && typeof sessions.variant !== "string")
    throw new Error("sessions.variant must be a string or null");
  if (dream.variant !== null && typeof dream.variant !== "string")
    throw new Error("dream.variant must be a string or null");
  if (sessions.opencodeUrl !== null && typeof sessions.opencodeUrl !== "string")
    throw new Error("sessions.opencodeUrl must be a string or null");
  if (
    !Number.isInteger(search.maxResults) ||
    search.maxResults < 1 ||
    search.maxResults > 200 ||
    !Number.isFinite(search.halfLifeDays) ||
    search.halfLifeDays <= 0 ||
    ![search.minScore, search.minSemanticScore].every(
      (value) => Number.isFinite(value) && value >= 0 && value <= 1,
    )
  )
    throw new Error("invalid search settings");
  const embedding = serviceEndpoint(
    (source.embedding ?? null) as Record<string, unknown> | null,
    "embedding",
    (url, model) => defaultEmbedding(url, model) as unknown as Record<string, unknown>,
    (merged) => {
      if (merged.queryInstruction !== null && typeof merged.queryInstruction !== "string")
        throw new Error("embedding.queryInstruction must be a string or null");
      merged.queryInstruction =
        typeof merged.queryInstruction === "string" ? merged.queryInstruction : null;
      merged.documentPrefix = optionalText(merged.documentPrefix, "embedding", "documentPrefix");
      merged.queryPrefix = optionalText(merged.queryPrefix, "embedding", "queryPrefix");
      merged.bearerEnv = bearerEnvName(merged.bearerEnv, "embedding");
      merged.timeoutMs = boundedInt(
        merged.timeoutMs,
        "embedding",
        "timeoutMs",
        1,
        Number.MAX_SAFE_INTEGER,
      );
      merged.maxBatchTexts = boundedInt(merged.maxBatchTexts, "embedding", "maxBatchTexts", 1, 512);
      merged.maxTextChars = boundedInt(
        merged.maxTextChars,
        "embedding",
        "maxTextChars",
        256,
        1_000_000,
      );
    },
  ) as unknown as EmbeddingSettings | null;
  const reranker = serviceEndpoint(
    (source.reranker ?? null) as Record<string, unknown> | null,
    "reranker",
    (url, model) => defaultReranker(url, model) as unknown as Record<string, unknown>,
    (merged) => {
      merged.bearerEnv = bearerEnvName(merged.bearerEnv, "reranker");
      merged.timeoutMs = boundedInt(
        merged.timeoutMs,
        "reranker",
        "timeoutMs",
        1,
        Number.MAX_SAFE_INTEGER,
      );
      merged.candidates = boundedInt(merged.candidates, "reranker", "candidates", 1, 1000);
      // Scores are ranking signals whose scale depends on the model, so the
      // threshold is any finite non-negative number, not a probability bound.
      if (!Number.isFinite(merged.minScore) || (merged.minScore as number) < 0)
        throw new Error("invalid reranker.minScore; expected a finite number of at least 0");
      merged.maxDocuments = boundedInt(merged.maxDocuments, "reranker", "maxDocuments", 1, 512);
      merged.maxChars = boundedInt(merged.maxChars, "reranker", "maxChars", 256, 1_000_000);
    },
  ) as unknown as RerankerSettings | null;
  return {
    embedding,
    reranker,
    sessions,
    dream,
    search,
    archive: mergeSection(defaults.archive, source.archive as Record<string, unknown> | undefined),
  };
}

export async function loadSettings(settingsFile: string): Promise<MemomaticSettings> {
  try {
    return normalizeSettings(JSON.parse(await readFile(settingsFile, "utf8")));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return defaultSettings();
    throw error;
  }
}

/** Splits long text at paragraph, line or space boundaries within the budget. */
export function chunkText(text: string, maxChars: number): string[] {
  if (text.length <= maxChars) return [text];
  const chunks: string[] = [];
  let start = 0;
  while (start < text.length) {
    let end = Math.min(start + maxChars, text.length);
    if (end < text.length) {
      const window = text.slice(start, end);
      const boundary = Math.max(
        window.lastIndexOf("\n\n"),
        window.lastIndexOf("\n"),
        window.lastIndexOf(" "),
      );
      if (boundary >= Math.floor(maxChars / 2)) end = start + boundary + 1;
    }
    const chunk = text.slice(start, end).trim();
    if (chunk) chunks.push(chunk);
    start = end;
  }
  return chunks.length ? chunks : [text.slice(0, maxChars)];
}

function bearerToken(bearerEnv: string | null, service: string): string | undefined {
  if (!bearerEnv) return undefined;
  const token = process.env[bearerEnv];
  if (!token) throw new Error(`${service} bearerEnv "${bearerEnv}" is not set`);
  return token;
}

async function postJson(
  url: string,
  body: unknown,
  token: string | undefined,
  timeoutMs: number,
  signal: AbortSignal | undefined,
  service: string,
): Promise<unknown> {
  const response = await fetch(url, {
    body: JSON.stringify(body),
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    method: "POST",
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)])
      : AbortSignal.timeout(timeoutMs),
  }).catch((error: unknown) => {
    const failure = error as Error;
    if (failure.name === "TimeoutError")
      throw new Error(`${service} request timed out after ${timeoutMs}ms`);
    if (failure.name === "AbortError") throw new Error(`${service} request was aborted`);
    throw new Error(`${service} request failed: ${failure.message}`);
  });
  if (!response.ok)
    throw new Error(
      `${service} request failed: ${response.status} ${(await response.text()).slice(0, 2000)}`,
    );
  try {
    return await response.json();
  } catch {
    throw new Error(`${service} response is not valid JSON`);
  }
}

export const MEMORY_QUERY_INSTRUCTION =
  "Given a search query, retrieve relevant personal memory entries that answer the query.";

export function embeddingQueryText(embedding: EmbeddingSettings, query: string): string {
  const instruction =
    embedding.queryInstruction ??
    (/qwen3[-_]?embedding/i.test(embedding.model) ? MEMORY_QUERY_INSTRUCTION : "");
  const wrapped = instruction ? `Instruct: ${instruction}\nQuery:${query}` : query;
  return `${embedding.queryPrefix}${wrapped}`;
}

export function embeddingDocumentText(embedding: EmbeddingSettings, text: string): string {
  return `${embedding.documentPrefix}${text}`;
}

function parseEmbeddingPayload(payload: unknown, count: number): Float32Array[] {
  const list = ((payload as { data?: unknown }).data ?? []) as Array<{
    embedding?: number[];
    index?: number;
  }>;
  if (!Array.isArray(list) || list.length !== count)
    throw new Error("embedding response is incomplete");
  const byIndex = new Map<number, number[]>();
  for (const item of list) {
    if (
      !Array.isArray(item.embedding) ||
      !item.embedding.length ||
      !item.embedding.every((value) => typeof value === "number" && Number.isFinite(value)) ||
      !item.embedding.some((value) => value !== 0)
    )
      throw new Error("embedding response is malformed");
    const index = item.index ?? byIndex.size;
    if (!Number.isInteger(index) || index < 0 || index >= count || byIndex.has(index))
      throw new Error("embedding response has invalid indices");
    byIndex.set(index, item.embedding);
  }
  const vectors = Array.from({ length: count }, (_, index) =>
    Float32Array.from(byIndex.get(index)!),
  );
  if (
    !vectors.every((vector) => vector.length === vectors[0].length && vector.every(Number.isFinite))
  )
    throw new Error("embedding response has incompatible vectors");
  return vectors;
}

function meanPool(vectors: Float32Array[]): Float32Array {
  if (vectors.length === 1) return vectors[0];
  const pooled = new Float32Array(vectors[0].length);
  for (const vector of vectors) {
    if (vector.length !== pooled.length)
      throw new Error("embedding response has incompatible vectors");
    for (let index = 0; index < vector.length; index += 1) pooled[index] += vector[index];
  }
  for (let index = 0; index < pooled.length; index += 1) pooled[index] /= vectors.length;
  return pooled;
}

/**
 * Embeds texts through an OpenAI-compatible `embeddings` endpoint. Long inputs
 * are split with chunkText, embedded chunk-wise and mean-pooled back onto one
 * vector per input text. Request character budgets are a conservative proxy,
 * not exact tokenization.
 */
export async function embedTexts(
  settings: MemomaticSettings,
  texts: string[],
  purpose: "document" | "query" = "document",
  signal?: AbortSignal,
): Promise<Float32Array[] | null> {
  if (!settings.embedding || !texts.length) return null;
  const embedding = settings.embedding;
  const token = bearerToken(embedding.bearerEnv, "embedding");
  const chunkLists = texts.map((text) =>
    chunkText(
      purpose === "query"
        ? embeddingQueryText(embedding, text)
        : embeddingDocumentText(embedding, text),
      embedding.maxTextChars,
    ),
  );
  const chunks = chunkLists.flat();
  const vectors = new Array<Float32Array>(chunks.length);
  for (let start = 0; start < chunks.length; start += embedding.maxBatchTexts) {
    const batch = chunks.slice(start, start + embedding.maxBatchTexts);
    const payload = await postJson(
      embedding.url,
      { input: batch, model: embedding.model, encoding_format: "float" },
      token,
      embedding.timeoutMs,
      signal,
      "embedding",
    );
    parseEmbeddingPayload(payload, batch.length).forEach(
      (vector, index) => (vectors[start + index] = vector),
    );
  }
  const pooled: Float32Array[] = [];
  let offset = 0;
  for (const list of chunkLists) {
    pooled.push(meanPool(vectors.slice(offset, offset + list.length)));
    offset += list.length;
  }
  return pooled;
}

export type RerankHit = { index: number; score: number };

function parseRerankResults(payload: unknown, count: number, offset: number): RerankHit[] {
  const results = (payload as { results?: unknown }).results;
  if (!Array.isArray(results)) throw new Error("reranker response is missing results");
  const seen = new Set<number>();
  const hits: RerankHit[] = [];
  for (const item of results) {
    const record = item as { index?: unknown; relevance_score?: unknown } | null;
    const index = record?.index;
    const score = record?.relevance_score;
    if (!Number.isInteger(index) || (index as number) < 0 || (index as number) >= count)
      throw new Error("reranker response has invalid indices");
    if (typeof score !== "number" || !Number.isFinite(score))
      throw new Error("reranker response is malformed");
    if (seen.has(index as number)) throw new Error("reranker response has invalid indices");
    seen.add(index as number);
    hits.push({ index: offset + (index as number), score });
  }
  return hits;
}

/**
 * Ranks documents against a query through a `/rerank`-style endpoint
 * (`{model, query, documents, top_n}` request, `results[].index` and
 * `results[].relevance_score` response). Long documents are chunked so the
 * query, one document chunk and the server template stay inside maxChars;
 * chunk scores aggregate to one best score per input document.
 */
export async function rerankTexts(
  settings: MemomaticSettings,
  query: string,
  documents: string[],
  signal?: AbortSignal,
): Promise<RerankHit[]> {
  const reranker = settings.reranker;
  if (!reranker || !documents.length) return [];
  const token = bearerToken(reranker.bearerEnv, "reranker");
  const formattedQuery = query.slice(0, reranker.maxChars);
  const budget = Math.max(
    256,
    reranker.maxChars - RERANKER_TEMPLATE_ALLOWANCE_CHARS - formattedQuery.length,
  );
  const chunkLists = documents.map((document) => chunkText(document, budget));
  const offsets: number[] = [];
  let total = 0;
  for (const list of chunkLists) {
    offsets.push(total);
    total += list.length;
  }
  const scores = new Map<number, number>();
  const chunks = chunkLists.flat();
  for (let start = 0; start < total; start += reranker.maxDocuments) {
    const batch = chunks.slice(start, start + reranker.maxDocuments);
    const payload = await postJson(
      reranker.url,
      {
        model: reranker.model,
        query: formattedQuery,
        documents: batch,
        top_n: batch.length,
      },
      token,
      reranker.timeoutMs,
      signal,
      "reranker",
    );
    for (const { index, score } of parseRerankResults(payload, batch.length, start))
      scores.set(index, Math.max(scores.get(index) ?? Number.NEGATIVE_INFINITY, score));
  }
  const hits: RerankHit[] = [];
  chunkLists.forEach((list, index) => {
    let best: number | null = null;
    for (let offset = 0; offset < list.length; offset += 1) {
      const score = scores.get(offsets[index] + offset);
      if (score !== undefined && (best === null || score > best)) best = score;
    }
    if (best !== null) hits.push({ index, score: best });
  });
  return hits.sort((left, right) => right.score - left.score || left.index - right.index);
}

export function embeddingFingerprint(settings: MemomaticSettings): string {
  return createHash("sha256")
    .update(
      JSON.stringify(
        settings.embedding
          ? {
              url: settings.embedding.url,
              model: settings.embedding.model,
              document: {
                prefix: settings.embedding.documentPrefix,
                maxChars: settings.embedding.maxTextChars,
                pooling: "mean-v1",
              },
            }
          : null,
      ),
    )
    .digest("hex");
}
