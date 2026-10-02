import {
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
  mkdtempSync,
  rmSync,
} from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync, spawn } from "node:child_process";
import {
  WorkflowError,
  artifactPayload,
  readJson,
  writeArtifact,
  writeCompanion,
  privateDirectory,
  redact,
} from "../contract.js";
import { commandArgv, sendCommand, shellJoin } from "../publication.js";
import { xdgStateHome } from "../state-artifacts.js";
import {
  BASELINE_NAME,
  buildFindingLedger,
  publishReviewState,
  rejectVisibleRawRefs,
  renderPublicationPatchCommand,
  codeFence,
  REVIEW_CONTRACT_VERSION,
  validateGitPatch,
  reviewMarkdown,
  validateSuggestion,
} from "../context.js";
import { createHash } from "node:crypto";
import { suggestionsPatch } from "../fixes.js";
import { stringsFor, type Strings } from "./strings.js";

export type Json = Record<string, unknown>;
const successfulReplies = new Set<string>();

export type PlanAction = {
  id: string;
  kind: string;
  publication_id: string | null;
  operation: string;
  command: string;
  path: string | null;
  line: number | null;
};

export type PlanBody = {
  publication_id: string;
  revision: number;
  kind: string;
  path: string;
  content: string;
};

export type PlanBundle = {
  root: string;
  planPath: string;
  planDigest: string;
  plan: Json;
  progress: Json;
  context?: Json;
};

export type ItemKind = "thread" | "line" | "general" | "issue" | "labels";

export type PlanItem = {
  key: string;
  kind: ItemKind;
  title: string;
  path: string | null;
  line: number | null;
  publicationId: string | null;
  body: string | null;
  actions: PlanAction[];
  detail: Json;
  url: string | null;
  conversation: Json[];
};

function sha256Text(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function shlexSplit(command: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let quoted: string | null = null;
  for (let index = 0; index < command.length; index += 1) {
    const char = command[index];
    if (quoted !== null) {
      if (char === quoted) quoted = null;
      else current += char;
      continue;
    }
    if (char === "'" || char === '"') {
      quoted = char;
      continue;
    }
    if (char === " " || char === "\t") {
      if (current !== "") tokens.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  if (current !== "") tokens.push(current);
  return tokens;
}

export function findReviewRoots(base: string): string[] {
  if (!existsSync(base)) return [];
  const found: string[] = [];
  const walk = (directory: string, depth: number): void => {
    if (depth > 6) return;
    let entries;
    try {
      entries = readdirSync(directory, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name === "review-current.json") {
        found.push(directory);
        continue;
      }
      if (entry.isDirectory() && !entry.name.startsWith(".")) {
        walk(join(directory, entry.name), depth + 1);
      }
    }
  };
  walk(base, 0);
  return found;
}

export function discoverArtifactRoot(): string | null {
  const base = join(xdgStateHome().toString(), "agent-skills", "gitlab");
  const candidates = findReviewRoots(base)
    .map((root) => {
      try {
        const progress = readJson(join(root, "review-current.json"), "code-review progress");
        return {
          root,
          stage: progress.stage,
          mtime: statSync(join(root, "review-current.json")).mtimeMs,
        };
      } catch {
        return null;
      }
    })
    .filter(
      (item): item is { root: string; stage: unknown; mtime: number } =>
        item !== null && item.stage === "plan_ready",
    )
    .sort((left, right) => right.mtime - left.mtime);
  return candidates.length > 0 ? candidates[0].root : null;
}

export function loadPlan(root: string): PlanBundle {
  let progress = readJson(join(root, "review-current.json"), "code-review progress");
  if (progress.stage !== "plan_ready") {
    const baselinePath = join(root, BASELINE_NAME);
    if (!existsSync(baselinePath))
      throw new WorkflowError(`the review is not finalized; current stage is ${progress.stage}`);
    const baseline = readJson(baselinePath, "last finalized review");
    const [, prior] = artifactPayload(String(baseline.plan_path), "review_plan");
    progress = {
      ...progress,
      stage: "plan_ready",
      plan_path: baseline.plan_path,
      plan_digest: baseline.plan_digest,
      evidence_path: `${root}/artifacts/evidence_snapshot/${prior.evidence_digest}.json`,
      context_path: `${root}/artifacts/review_context/${prior.context_digest}.json`,
      decision_path: `${root}/artifacts/review_decision/${prior.decision_digest}.json`,
    };
  }
  const planPath = String(progress.plan_path);
  const planDigest = String(progress.plan_digest);
  const data = readFileSync(planPath);
  if (sha256Text(data.toString()) !== planDigest) {
    throw new WorkflowError("review plan digest changed");
  }
  const [, plan] = artifactPayload(planPath, "review_plan") as [Json, Json];
  const [, context] = artifactPayload(String(progress.context_path), "review_context");
  return { root, planPath, planDigest, plan, progress, context };
}

export function planItems(bundle: PlanBundle): PlanItem[] {
  const plan = bundle.plan;
  const preview = (plan.publication_preview as Json) ?? { actions: [], body_files: [] };
  const actions = (preview.actions as PlanAction[]) ?? [];
  const bodies = (preview.body_files as PlanBody[]) ?? [];
  const bodyByPublication = new Map<string, PlanBody>();
  for (const body of bodies) bodyByPublication.set(body.publication_id, body);
  const actionsByPublication = new Map<string, PlanAction[]>();
  for (const action of actions) {
    if (action.publication_id === null) continue;
    const list = actionsByPublication.get(action.publication_id) ?? [];
    list.push(action);
    actionsByPublication.set(action.publication_id, list);
  }
  const items: PlanItem[] = [];
  const discussions = (bundle.context?.discussions ?? []) as Json[];
  const findings = new Map(
    ((plan.findings ?? []) as Json[]).map((item) => [String(item.id), item]),
  );
  for (const decision of (plan.thread_decisions as Json[]) ?? []) {
    const publicationId = `thread-${decision.id}`;
    const bodyRecord = bodyByPublication.get(publicationId);
    const source = discussions.find((item) => String(item.root_note_id) === String(decision.id));
    const position = (source?.root_position ?? decision.expectation ?? {}) as Json;
    const conversation = (source?.notes ??
      ((bundle.context?.notes ?? []) as Json[]).filter(
        (note) => String(note.id) === String(decision.id),
      )) as Json[];
    const first = conversation.find((note) => note.system !== true);
    const path = (position.new_path ?? position.old_path ?? position.path ?? null) as string | null;
    const line = (position.new_line ?? position.old_line ?? position.line ?? null) as number | null;
    items.push({
      key: publicationId,
      kind: "thread",
      title:
        typeof decision.summary === "string" && decision.summary !== ""
          ? decision.summary
          : displayText(
              String(first?.body ?? decision.rationale ?? `discussion ${decision.id}`),
            ).split("\n")[0],
      path,
      line,
      publicationId,
      body: bodyRecord?.content ?? null,
      actions: actionsByPublication.get(publicationId) ?? [],
      detail: decision,
      url: typeof decision.url === "string" ? decision.url : null,
      conversation,
    });
  }
  for (const publication of (plan.finding_publications as Json[]) ?? []) {
    const publicationId = String(publication.finding_id ?? publication.id ?? "");
    const bodyRecord = bodyByPublication.get(publicationId);
    const own = actionsByPublication.get(publicationId) ?? [];
    const position = own.find((action) => action.path !== null) ?? null;
    const isLine =
      own.some((action) => action.operation === "create_line") ||
      (publication.position !== null && typeof publication.position === "object");
    items.push({
      key: publicationId,
      kind: isLine ? "line" : "general",
      title:
        typeof publication.title === "string" && publication.title !== ""
          ? publication.title
          : String(findings.get(publicationId)?.summary ?? publication.finding_id ?? publicationId),
      path: position?.path ?? ((publication.position as Json)?.new_path as string) ?? null,
      line: position?.line ?? ((publication.position as Json)?.new_line as number) ?? null,
      publicationId,
      body: bodyRecord?.content ?? (typeof publication.body === "string" ? publication.body : null),
      actions: own,
      detail: publication,
      url:
        typeof (plan.target as Json)?.url === "string" ? String((plan.target as Json).url) : null,
      conversation: [],
    });
  }
  for (const issue of (plan.recommended_issues as Json[]) ?? []) {
    const publicationId = String(issue.id ?? issue.title ?? "");
    const bodyRecord = bodyByPublication.get(publicationId);
    items.push({
      key: publicationId,
      kind: "issue",
      title: String(issue.title ?? publicationId),
      path: null,
      line: null,
      publicationId,
      body: bodyRecord?.content ?? null,
      actions: actionsByPublication.get(publicationId) ?? [],
      detail: issue,
      url: null,
      conversation: [],
    });
  }
  const labels = (plan.label_review as Json) ?? null;
  for (const action of actions.filter((action) =>
    action.publication_id?.includes("@suggestion-"),
  )) {
    const publicationId = action.publication_id!;
    const ownerId = publicationId.split("@suggestion-")[0];
    const owner = items.find((item) => item.publicationId === ownerId);
    const body = bodyByPublication.get(publicationId)?.content ?? null;
    items.push({
      key: publicationId,
      kind: "line",
      title: `${owner?.title ?? ownerId} (${publicationId.split("@suggestion-")[1]})`,
      path: action.path,
      line: action.line,
      publicationId,
      body,
      actions: [action],
      detail: { fix_mode: "suggestion", body, path: action.path, line: action.line, patch: null },
      url: owner?.url ?? null,
      conversation: [],
    });
  }
  if (
    labels !== null &&
    (((labels.add ?? []) as unknown[]).length > 0 ||
      ((labels.remove ?? []) as unknown[]).length > 0)
  ) {
    const addAction = actions.find((action) => action.kind === "labels") ?? null;
    items.push({
      key: "labels:update",
      kind: "labels",
      title: stringsFor(String(plan.locale ?? "en")).labels,
      path: null,
      line: null,
      publicationId: null,
      body: null,
      actions: addAction !== null ? [addAction] : [],
      detail: labels,
      url: null,
      conversation: [],
    });
  }
  if (
    plan.review_contract_version !== undefined &&
    plan.review_contract_version !== REVIEW_CONTRACT_VERSION
  )
    return items.map((item) => ({ ...item, actions: [] }));
  return items;
}

export function displayText(value: string): string {
  return value
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\x00-\x08\x0b-\x1f\x7f]/g, "");
}

export function readableMarkdown(value: string): string {
  let fence = 0;
  return value
    .split("\n")
    .map((line) => {
      const boundary = /^(`{3,})([^`]*)$/.exec(line);
      if (boundary && (fence === 0 || boundary[1].length >= fence)) {
        if (fence > 0) {
          fence = 0;
          return "";
        }
        fence = boundary[1].length;
        return boundary[2].trim() === "" ? "" : `[${boundary[2].trim()}]`;
      }
      if (fence > 0) return line;
      return line
        .replace(/^#{1,6}\s+/, "")
        .replace(/\*\*([^*]+)\*\*/g, "$1")
        .replace(/`([^`]+)`/g, "$1")
        .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, "$1 ($2)");
    })
    .join("\n");
}

export function safeLink(value: string | null): string | null {
  if (value === null || /[\x00-\x20\x7f]/.test(value)) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.username === "" && url.password === ""
      ? url.href
      : null;
  } catch {
    return null;
  }
}

export function terminalLink(
  value: string | null,
  enabled = process.stdout.isTTY === true && process.env.TERM !== "dumb",
  label?: string,
): string {
  const url = safeLink(value);
  if (url === null) return "";
  return enabled ? `\x1b]8;;${url}\x07${displayText(label ?? url)}\x1b]8;;\x07` : url;
}

export function browserCommand(value: string, platform: string = process.platform): string[] {
  const url = safeLink(value);
  if (url === null) throw new WorkflowError("Discussion link must be a safe HTTPS URL");
  return platform === "darwin"
    ? ["open", url]
    : platform === "win32"
      ? ["rundll32", "url.dll,FileProtocolHandler", url]
      : ["xdg-open", url];
}

export async function openLink(value: string): Promise<void> {
  const [executable, ...args] = browserCommand(value);
  const child = spawn(executable, args, { stdio: "ignore" });
  await new Promise<void>((resolve, reject) => {
    child.once("error", reject);
    child.once("spawn", resolve);
  });
  child.unref();
}

export function itemText(
  item: PlanItem,
  strings: Strings = stringsFor("en"),
  editedBody?: string,
): string {
  const lines: string[] = [];
  if (item.kind === "thread") {
    lines.push(
      `${strings.discussion} · ${String(item.detail.state ?? "")} · ${String(item.detail.outcome ?? "")}`,
      "",
    );
    for (const note of item.conversation) {
      const author = (note.author ?? {}) as Json;
      lines.push(
        `@${String(author.username ?? note.author_username ?? "?")} ${String(note.created_at ?? "")}${note.system === true ? ` [${strings.systemNote}]` : ""}`,
        String(note.body ?? ""),
        "",
      );
    }
    lines.push(
      `${strings.assessment}: ${String(item.detail.assessment ?? "")}`,
      String(item.detail.rationale ?? ""),
      "",
    );
  }
  if (item.kind === "labels") {
    lines.push(
      `${strings.labelsAdd}: ${((item.detail.add ?? []) as string[]).join(", ") || "-"}`,
      `${strings.labelsRemove}: ${((item.detail.remove ?? []) as string[]).join(", ") || "-"}`,
    );
  } else {
    lines.push(`${strings.replyDraft}:`, editedBody ?? item.body ?? strings.noPublication);
    if (
      item.detail.fix_mode === "patch" &&
      typeof item.detail.patch === "string" &&
      !(item.body ?? "").includes(item.detail.patch)
    )
      lines.push("", `${strings.patch}:`, item.detail.patch);
  }
  return displayText(lines.join("\n"));
}

export function selectedActions(refreshed: PlanAction[], selected: PlanAction[]): PlanAction[] {
  const ids = new Set(selected.map((action) => action.id));
  return refreshed.filter((action) => ids.has(action.id));
}

export function visualLines(text: string, width: number): string[] {
  const result: string[] = [];
  const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  for (const line of displayText(text).replace(/\n$/, "").split("\n")) {
    let row = "",
      length = 0;
    for (const { segment } of segmenter.segment(line)) {
      const size =
        /\p{Extended_Pictographic}|[\u1100-\u115f\u2e80-\ua4cf\uac00-\ud7a3\uf900-\ufaff\uff01-\uff60]/u.test(
          segment,
        )
          ? 2
          : segment === "\t"
            ? 4
            : 1;
      if (length + size > Math.max(2, width) && row !== "") {
        result.push(row);
        row = "";
        length = 0;
      }
      row += segment === "\t" ? "    " : segment;
      length += size;
    }
    result.push(row);
  }
  return result;
}

async function planArtifacts(bundle: PlanBundle): Promise<{ evidence: Json; context: Json }> {
  const evidencePath = String(bundle.progress.evidence_path);
  const contextPath = String(bundle.progress.context_path);
  const [, evidence] = artifactPayload(evidencePath, "evidence_snapshot") as [Json, Json];
  const [, context] = artifactPayload(contextPath, "review_context") as [Json, Json];
  return { evidence, context };
}

async function argvForAction(options: {
  action: PlanAction;
  bodyPath: string;
  evidence: Json;
}): Promise<string[]> {
  return commandArgv(options.action.command).map((token) =>
    /^(body|description)=@/.test(token) ? `${token.split("=")[0]}=@${options.bodyPath}` : token,
  );
}

export async function amendBody(
  bundle: PlanBundle,
  publicationId: string,
  body: string,
): Promise<PlanBundle> {
  if (bundle.plan.review_contract_version !== REVIEW_CONTRACT_VERSION)
    throw new WorkflowError("Only new plans support repair; historical plans are read-only");
  const { evidence, context } = await planArtifacts(bundle);
  const normalized = `${body.replace(/\s+$/, "")}\n`;
  const item = planItems(bundle).find((candidate) => candidate.publicationId === publicationId);
  if (item === undefined || item.actions.length === 0)
    throw new WorkflowError("This item has no editable publication body");
  const routingReply =
    item.kind === "thread" &&
    Array.isArray(item.detail.suggestions) &&
    item.body !== null &&
    !/^```suggestion/m.test(item.body);
  if (routingReply && /^```suggestion|^diff --git |git\s+apply\s*(?:<<|--)/m.test(normalized))
    throw new WorkflowError(
      "A routing-only reply must remain prose; use targeted fix repair to change suggestions or patches",
    );
  if (item.detail.fix_mode === "suggestion" && !routingReply) {
    validateSuggestion(normalized, {
      repoRoot: String((context.exact_git as Json).repo_root),
      headSha: String(evidence.head_sha),
      path: item.path!,
      line: item.line!,
    });
    if (item.body !== null) {
      const repo = String((context.exact_git as Json).repo_root),
        head = String(evidence.head_sha);
      const oldTree: { tree?: string } = {},
        newTree: { tree?: string } = {};
      validateGitPatch(
        repo,
        head,
        suggestionsPatch(repo, head, [{ path: item.path!, line: item.line!, body: item.body }]),
        oldTree,
      );
      validateGitPatch(
        repo,
        head,
        suggestionsPatch(repo, head, [{ path: item.path!, line: item.line!, body: normalized }]),
        newTree,
      );
      if (oldTree.tree !== newTree.tree)
        throw new WorkflowError(
          "Changed suggestion code requires targeted fix repair, not body editing",
        );
    }
  }
  if (
    item.detail.fix_mode === "patch" &&
    typeof item.detail.patch === "string" &&
    !normalized.includes(item.detail.patch.trim())
  )
    throw new WorkflowError(
      "Body editing must preserve the validated patch; prepare a new review draft to change the code fix",
    );
  let semanticBody = normalized;
  if (item.detail.fix_mode === "patch") {
    const suffix = `\n\n${item.detail.patch_reason}\n\n${codeFence(renderPublicationPatchCommand(item.detail), "sh")}\n`;
    if (!normalized.endsWith(suffix))
      throw new WorkflowError("Body editing must preserve the validated patch command");
    semanticBody = normalized.slice(0, -suffix.length).trimEnd();
  }
  const bodyDirectory = await privateDirectory(
    join(bundle.root, "artifacts", "review_plan", "bodies"),
  );
  const identityDigest = sha256Text(publicationId).slice(0, 12);
  const contentDigest = sha256Text(normalized).slice(0, 12);
  const [bodyPath] = writeCompanion(
    join(bodyDirectory, `${identityDigest}-${contentDigest}.md`),
    normalized,
  );
  const preview = bundle.plan.publication_preview as Json;
  const actions = structuredClone((preview.actions as PlanAction[]) ?? []);
  const group = actions.filter((action) => action.publication_id === publicationId);
  for (const action of group) {
    const argv = await argvForAction({ evidence, action, bodyPath });
    action.command = shellJoin(argv);
  }
  const bodyFiles = ((preview.body_files as PlanBody[]) ?? []).map((record) =>
    record.publication_id === publicationId
      ? { ...record, path: bodyPath, content: normalized }
      : record,
  );
  if (!bodyFiles.some((record) => record.publication_id === publicationId)) {
    bodyFiles.push({
      publication_id: publicationId,
      revision: 1,
      kind: group[0]?.kind ?? "finding",
      path: bodyPath,
      content: normalized,
    });
  }
  const nextPlan: Json = {
    ...bundle.plan,
    publication_preview: { ...preview, actions, body_files: bodyFiles },
  };
  const [ownerId, partNumber] = publicationId.split("@suggestion-");
  const updatePart = (record: Json, thread: boolean): Json => {
    if ((thread ? `thread-${record.id}` : String(record.finding_id)) !== ownerId) return record;
    const partBody = normalized.trimEnd();
    return {
      ...record,
      suggestions: (record.suggestions as Json[]).map((part, index) =>
        index + 1 === Number(partNumber) ? { ...part, body: partBody } : part,
      ),
    };
  };
  const updateThread = (record: Json): Json => {
    if (`thread-${record.id}` !== publicationId) return record;
    if (routingReply) return { ...record, routing_response: semanticBody };
    if (
      Array.isArray(record.suggestions) &&
      record.suggestions.some((part: Json) => part.path === item.path && part.line === item.line)
    )
      return {
        ...record,
        suggestions: (record.suggestions as Json[]).map((part) =>
          part.path === item.path && part.line === item.line
            ? { ...part, body: semanticBody }
            : part,
        ),
      };
    return { ...record, proposed_response: semanticBody };
  };
  if (partNumber !== undefined) {
    nextPlan.thread_decisions = (bundle.plan.thread_decisions as Json[]).map((record) =>
      updatePart(record, true),
    );
    nextPlan.finding_publications = (bundle.plan.finding_publications as Json[]).map((record) =>
      updatePart(record, false),
    );
  } else if (item.kind === "thread")
    nextPlan.thread_decisions = ((bundle.plan.thread_decisions ?? []) as Json[]).map((record) =>
      updateThread(record),
    );
  else if (item.kind === "issue")
    nextPlan.recommended_issues = ((bundle.plan.recommended_issues ?? []) as Json[]).map(
      (record) =>
        String(record.id) === publicationId ? { ...record, body: semanticBody } : record,
    );
  else
    nextPlan.finding_publications = ((bundle.plan.finding_publications ?? []) as Json[]).map(
      (record) =>
        String(record.finding_id) === publicationId ? { ...record, body: semanticBody } : record,
    );
  nextPlan.finding_ledger = buildFindingLedger(
    nextPlan.incremental as Json,
    nextPlan.previous_finding_assessments as Json[],
    nextPlan.findings as Json[],
    nextPlan.finding_publications as Json[],
    nextPlan.recommended_issues as Json[],
    nextPlan.publication_preview as Json,
  );
  const [, decision] = artifactPayload(String(bundle.progress.decision_path), "review_decision");
  if (bundle.plan.review_source !== undefined) {
    const source = structuredClone(bundle.plan.review_source) as Json;
    const sourceContent = source.content as Json;
    const key =
      partNumber !== undefined
        ? ownerId.startsWith("thread-")
          ? "thread_decisions"
          : "finding_publications"
        : item.kind === "thread"
          ? "thread_decisions"
          : item.kind === "issue"
            ? "recommended_issues"
            : "finding_publications";
    sourceContent[key] = (sourceContent[key] as Json[]).map((record) => {
      if (partNumber !== undefined) return updatePart(record, key === "thread_decisions");
      if (key === "thread_decisions") return updateThread(record);
      const id = String(record.finding_id ?? record.id);
      return id === publicationId ? { ...record, body: semanticBody } : record;
    });
    nextPlan.review_source = source;
  }
  const markdown = await reviewMarkdown(
    evidence,
    context,
    decision,
    nextPlan,
    nextPlan.mr_metadata_assessment as Json,
    nextPlan.publication_preview as Json,
  );
  rejectVisibleRawRefs(markdown, evidence, context);
  nextPlan.markdown = markdown;
  const [planPath, planDigest] = await writeArtifact(bundle.root, "review_plan", nextPlan);
  const baselineDigest = sha256Text(readFileSync(join(bundle.root, BASELINE_NAME), "utf8"));
  await publishReviewState(
    bundle.root,
    markdown,
    planPath,
    planDigest,
    context.target as Json,
    baselineDigest,
    { stage: "plan_ready", plan_path: bundle.planPath, plan_digest: bundle.planDigest },
  );
  return loadPlan(bundle.root);
}

export async function sendAction(
  bundle: PlanBundle,
  action: PlanAction,
  signal?: AbortSignal,
): Promise<Json> {
  if (bundle.plan.review_contract_version !== REVIEW_CONTRACT_VERSION)
    throw new WorkflowError("Historical plans are read-only; prepare a new runbook");
  const replyKey = `${bundle.planDigest}:${action.publication_id}`;
  if (["resolve", "reopen"].includes(action.operation) && !successfulReplies.has(replyKey))
    throw new WorkflowError(
      "Send the planned reply successfully before changing discussion state in this manual session",
    );
  const result = await sendCommand(action.command, signal);
  if (result.code === 0 && action.operation === "reply") successfulReplies.add(replyKey);
  if (result.code === 0 && action.operation === "reply") {
    const thread = ((bundle.plan.thread_decisions ?? []) as Json[]).find(
      (thread) => action.publication_id === `thread-${thread.id}`,
    );
    if (
      thread?.state === "plain" &&
      ["fixed", "false_positive", "duplicate", "not_related"].includes(String(thread.assessment))
    ) {
      let returned: Json;
      try {
        returned = JSON.parse(result.stdout.toString("utf8"));
      } catch {
        throw new WorkflowError(
          "Reply succeeded but its discussion identity is unavailable; inspect GitLab before any state change or retry",
        );
      }
      if (
        Array.isArray(returned.notes) &&
        (returned.notes as Json[]).some((note) => note.resolvable === true)
      ) {
        if (typeof returned.id !== "string" || !/^[A-Za-z0-9_-]+$/.test(returned.id))
          throw new WorkflowError(
            "Reply succeeded but returned an invalid discussion ID; no state change was made",
          );
        const argv = commandArgv(action.command);
        const endpointIndex = argv.findIndex((value) =>
          /^projects\/\d+\/merge_requests\/\d+\/discussions$/.test(value),
        );
        const resolved = await sendCommand(
          shellJoin([
            "glab",
            "api",
            "--hostname",
            argv[argv.indexOf("--hostname") + 1],
            "--method",
            "PUT",
            `${argv[endpointIndex]}/${returned.id}`,
            "--silent",
            "-F",
            "resolved=true",
          ]),
          signal,
        );
        if (resolved.code !== 0)
          return {
            status: "error",
            code: resolved.code,
            output: "Reply sent; discussion state update failed. Do not repeat the reply.",
            error: redact(resolved.stderr.toString("utf8")),
          };
      }
    }
  }
  return {
    status: result.code === 0 ? "sent" : "error",
    code: result.code,
    output: redact(result.stdout.toString("utf8")).slice(0, 4000),
    error: redact(result.stderr.toString("utf8")).slice(0, 4000),
  };
}

export async function sendItem(
  bundle: PlanBundle,
  item: PlanItem,
  editedBody: string | null,
  signal?: AbortSignal,
): Promise<{ bundle: PlanBundle; results: Json[] }> {
  let current = bundle;
  if (editedBody !== null && item.publicationId !== null) {
    current = await amendBody(current, item.publicationId, editedBody);
  }
  const refreshed =
    item.publicationId === null
      ? item.actions
      : (planItems(current).find((candidate) => candidate.key === item.key)?.actions ??
        item.actions);
  const ordered = selectedActions(refreshed, item.actions).sort((left, right) => {
    const order = (action: PlanAction): number =>
      action.operation === "resolve" || action.operation === "reopen" ? 1 : 0;
    return order(left) - order(right);
  });
  const results: Json[] = [];
  if (ordered.length === 0) throw new WorkflowError("This item has no selected publication action");
  for (const action of ordered) {
    const result = await sendAction(current, action, signal);
    results.push(result);
    if (result.status !== "sent") break;
  }
  return { bundle: current, results };
}

export function editInEditor(body: string): string | null {
  const editor = process.env.EDITOR ?? process.env.VISUAL ?? "vi";
  const args = shlexSplit(editor);
  if (args.length === 0) throw new WorkflowError("EDITOR must name an executable");
  const directory = mkdtempSync(join(tmpdir(), "reviewmatic-editor-"));
  const path = join(directory, "body.md");
  try {
    writeFileSync(path, body, { mode: 0o600 });
    const result = spawnSync(args[0], [...args.slice(1), path], {
      stdio: "inherit",
      timeout: 600000,
    });
    if (result.error || result.status !== 0) return null;
    const edited = readFileSync(path, "utf8");
    return edited === body ? null : edited;
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

export async function planRepository(
  bundle: PlanBundle,
): Promise<{ repoRoot: string | null; branch: string | null; headSha: string | null }> {
  const { evidence, context } = await planArtifacts(bundle);
  const object = evidence.object as Json;
  const exactGit = (context.exact_git as Json) ?? {};
  const diffRefs = (object.diff_refs as Json) ?? {};
  return {
    repoRoot: typeof exactGit.repo_root === "string" ? exactGit.repo_root : null,
    branch: typeof object.source_branch === "string" ? object.source_branch : null,
    headSha: typeof diffRefs.head_sha === "string" ? diffRefs.head_sha : null,
  };
}
