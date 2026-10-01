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
} from "../contract.js";
import { makeCommand, execute, loadAction } from "../publication.js";
import { xdgStateHome } from "../state-artifacts.js";
import {
  BASELINE_NAME,
  buildFindingLedger,
  publishReviewState,
  rejectVisibleRawRefs,
  renderPublicationPatchCommand,
  reviewMarkdown,
  validateSuggestion,
} from "../context.js";
import { createHash } from "node:crypto";
import { stringsFor, type Strings } from "./strings.js";

export type Json = Record<string, unknown>;

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
  const progress = readJson(join(root, "review-current.json"), "code-review progress");
  if (progress.stage !== "plan_ready") {
    throw new WorkflowError(`the review is not finalized; current stage is ${progress.stage}`);
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
  return items;
}

export function displayText(value: string): string {
  return value
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\x00-\x08\x0b-\x1f\x7f]/g, "");
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

export function commandTarget(command: string): { path: string; digest: string } {
  const tokens = shlexSplit(command);
  const actionIndex = tokens.indexOf("--action");
  const confirmIndex = tokens.indexOf("--confirm");
  if (actionIndex < 0 || confirmIndex < 0) {
    throw new WorkflowError("publication command is invalid");
  }
  return { path: tokens[actionIndex + 1], digest: tokens[confirmIndex + 1] };
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
  const target = commandTarget(options.action.command);
  const [, guard] = await loadAction(target.path, target.digest);
  const payload = guard.payload as Json;
  if (options.action.operation === "create_line") {
    const position = payload.position as Json;
    const side = "new_line" in position ? "new" : "old";
    return [
      "glab",
      "mr",
      "note",
      "create",
      String(guard.mr_iid),
      "--repo",
      String((options.evidence.object as Json).web_url).split("/-/merge_requests/")[0],
      "--file",
      String(position[`${side}_path`]),
      side === "new" ? "--line" : "--old-line",
      String(position[`${side}_line`]),
    ];
  }
  const argv = [
    "glab",
    "api",
    "--hostname",
    String(guard.host),
    "--method",
    String(guard.method),
    String(guard.endpoint),
    "--silent",
  ];
  for (const [key, value] of Object.entries(payload)) {
    if (key === "body" || key === "description") argv.push("-F", `${key}=@${options.bodyPath}`);
    else argv.push(key === "resolved" ? "-F" : "-f", `${key}=${value}`);
  }
  return argv;
}

export async function amendBody(
  bundle: PlanBundle,
  publicationId: string,
  body: string,
): Promise<PlanBundle> {
  const { evidence, context } = await planArtifacts(bundle);
  const normalized = `${body.replace(/\s+$/, "")}\n`;
  const item = planItems(bundle).find((candidate) => candidate.publicationId === publicationId);
  if (item === undefined || item.actions.length === 0)
    throw new WorkflowError("This item has no editable publication body");
  if (item.detail.fix_mode === "suggestion") {
    validateSuggestion(normalized, {
      repoRoot: String((context.exact_git as Json).repo_root),
      headSha: String(evidence.head_sha),
      path: item.path!,
      line: item.line!,
    });
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
    const suffix = `\n\n\`\`\`sh\n${renderPublicationPatchCommand(item.detail)}\n\`\`\`\n`;
    if (!normalized.endsWith(suffix))
      throw new WorkflowError("Body editing must preserve the validated patch command");
    semanticBody = normalized.slice(0, -suffix.length).trimEnd();
  }
  const bodyDirectory = await privateDirectory(
    join(bundle.root, "artifacts", "review_plan", "bodies"),
  );
  const identityDigest = sha256Text(publicationId).slice(0, 12);
  const contentDigest = sha256Text(normalized).slice(0, 12);
  const [bodyPath, bodyDigest] = writeCompanion(
    join(bodyDirectory, `${identityDigest}-${contentDigest}.md`),
    normalized,
  );
  const preview = bundle.plan.publication_preview as Json;
  const actions = structuredClone((preview.actions as PlanAction[]) ?? []);
  const dependencies: Record<string, string> = {};
  const group = actions.filter((action) => action.publication_id === publicationId);
  for (const action of group) {
    const argv = await argvForAction({ evidence, action, bodyPath });
    const value: Json =
      action.operation === "create_issue"
        ? {
            body_sha256: bodyDigest,
            title: argv[argv.indexOf("-f") + 1]?.replace("title=", "") ?? "",
          }
        : action.operation === "resolve" || action.operation === "reopen"
          ? { resolved: action.operation === "resolve" ? "true" : "false" }
          : { body_sha256: bodyDigest };
    action.command = await makeCommand(
      bundle.root,
      evidence,
      context,
      action.id,
      argv,
      value,
      dependencies,
      action.operation === "create_line" ? bodyDigest : null,
    );
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
  if (item.kind === "thread")
    nextPlan.thread_decisions = ((bundle.plan.thread_decisions ?? []) as Json[]).map((record) =>
      `thread-${record.id}` === publicationId
        ? { ...record, proposed_response: semanticBody }
        : record,
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

export async function sendAction(bundle: PlanBundle, action: PlanAction): Promise<Json> {
  const target = commandTarget(action.command);
  return (await execute(target.path, target.digest)) as Json;
}

export async function sendItem(
  bundle: PlanBundle,
  item: PlanItem,
  editedBody: string | null,
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
    const result = await sendAction(current, action);
    results.push(result);
    if (result.status === "blocked") break;
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
