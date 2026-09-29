import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import {
  WorkflowError,
  artifactPayload,
  readJson,
  writeArtifact,
  writeCompanion,
  privateDirectory,
} from "../contract.js";
import { makeCommand, execute } from "../publication.js";
import { xdgStateHome } from "../state-artifacts.js";
import { advanceProgress } from "../context.js";
import { createHash } from "node:crypto";

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
  const base = join(xdgStateHome().toString(), "agent-skills", "code-review");
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
  return { root, planPath, planDigest, plan, progress };
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
  for (const decision of (plan.thread_decisions as Json[]) ?? []) {
    const publicationId = `thread-${decision.id}`;
    const bodyRecord = bodyByPublication.get(publicationId);
    const position = (decision.expectation as Json) ?? {};
    items.push({
      key: publicationId,
      kind: "thread",
      title:
        typeof decision.summary === "string" && decision.summary !== ""
          ? decision.summary
          : `${position.path ?? "discussion"}${position.line ? `:${position.line}` : ""}`,
      path: (position.path as string) ?? null,
      line: (position.line as number) ?? null,
      publicationId,
      body: bodyRecord?.content ?? null,
      actions: actionsByPublication.get(publicationId) ?? [],
      detail: decision,
    });
  }
  for (const publication of (plan.finding_publications as Json[]) ?? []) {
    const publicationId = String(publication.finding_id ?? publication.id ?? "");
    const bodyRecord = bodyByPublication.get(publicationId);
    const own = actionsByPublication.get(publicationId) ?? [];
    const position = own.find((action) => action.path !== null) ?? null;
    const isLine =
      own.some((action) => action.operation === "create_line") ||
      (publication.position as Json) !== undefined;
    items.push({
      key: publicationId,
      kind: isLine ? "line" : "general",
      title:
        typeof publication.title === "string" && publication.title !== ""
          ? publication.title
          : String(publication.finding_id ?? publicationId),
      path: position?.path ?? ((publication.position as Json)?.new_path as string) ?? null,
      line: position?.line ?? ((publication.position as Json)?.new_line as number) ?? null,
      publicationId,
      body: bodyRecord?.content ?? null,
      actions: own,
      detail: publication,
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
    });
  }
  const labels = (plan.label_review as Json) ?? null;
  if (labels !== null) {
    const addAction = actions.find((action) => action.kind === "labels") ?? null;
    items.push({
      key: "labels:update",
      kind: "labels",
      title: "labels",
      path: null,
      line: null,
      publicationId: null,
      body: null,
      actions: addAction !== null ? [addAction] : [],
      detail: labels,
    });
  }
  return items;
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

function argvForAction(options: {
  evidence: Json;
  action: PlanAction;
  bodyPath: string;
  title?: string;
}): string[] {
  const project = options.evidence.project as Json;
  const target = options.evidence.target as Json;
  const object = options.evidence.object as Json;
  const hostname = String(project.hostname);
  const endpoint = `projects/${project.id}/merge_requests/${target.iid}`;
  const repositoryUrl = String(object.web_url).split("/-/merge_requests/")[0];
  switch (options.action.operation) {
    case "create_line": {
      const lineOption = options.action.line !== null ? "--line" : "--old-line";
      return [
        "glab",
        "mr",
        "note",
        "create",
        String(target.iid),
        "--repo",
        repositoryUrl,
        "--file",
        String(options.action.path),
        lineOption,
        String(options.action.line ?? 1),
      ];
    }
    case "create_general":
      return [
        "glab",
        "api",
        "--hostname",
        hostname,
        "--method",
        "POST",
        `${endpoint}/discussions`,
        "--silent",
        "-F",
        `body=@${options.bodyPath}`,
      ];
    case "create_issue":
      return [
        "glab",
        "api",
        "--hostname",
        hostname,
        "--method",
        "POST",
        `projects/${project.id}/issues`,
        "-f",
        `title=${options.title ?? ""}`,
        "--silent",
        "-F",
        `description=@${options.bodyPath}`,
      ];
    case "resolve":
    case "reopen": {
      const match = /discussions\/([A-Za-z0-9_-]+)/.exec(options.action.command);
      const discussionId = match !== null ? match[1] : null;
      if (discussionId === null) {
        throw new WorkflowError("thread state action requires a discussion");
      }
      return [
        "glab",
        "api",
        "--hostname",
        hostname,
        "--method",
        "PUT",
        `${endpoint}/discussions/${discussionId}`,
        "--silent",
        "-F",
        `resolved=${options.action.operation === "resolve" ? "true" : "false"}`,
      ];
    }
    default: {
      const match = /discussions\/([A-Za-z0-9_-]+)\/notes/.exec(options.action.command);
      if (match !== null) {
        return [
          "glab",
          "api",
          "--hostname",
          hostname,
          "--method",
          "POST",
          `${endpoint}/discussions/${match[1]}/notes`,
          "--silent",
          "-F",
          `body=@${options.bodyPath}`,
        ];
      }
      return [
        "glab",
        "api",
        "--hostname",
        hostname,
        "--method",
        "POST",
        `${endpoint}/notes`,
        "--silent",
        "-F",
        `body=@${options.bodyPath}`,
      ];
    }
  }
}

export async function amendBody(
  bundle: PlanBundle,
  publicationId: string,
  body: string,
): Promise<PlanBundle> {
  const { evidence, context } = await planArtifacts(bundle);
  const normalized = `${body.replace(/\s+$/, "")}\n`;
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
  const actions = [...((preview.actions as PlanAction[]) ?? [])];
  const dependencies: Record<string, string> = {};
  const group = actions.filter((action) => action.publication_id === publicationId);
  const issueTitle = String(
    ((bundle.plan.recommended_issues as Json[]) ?? []).find(
      (issue) => String(issue.id) === publicationId,
    )?.title ?? "",
  );
  for (const action of group) {
    const argv = argvForAction({ evidence, action, bodyPath, title: issueTitle });
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
  const nextPlan = {
    ...bundle.plan,
    publication_preview: { ...preview, actions, body_files: bodyFiles },
  };
  const [planPath, planDigest] = await writeArtifact(bundle.root, "review_plan", nextPlan);
  await advanceProgress(bundle.root, "plan_ready", {
    expectedStages: new Set(["plan_ready"]),
    expected: { plan_path: bundle.planPath, plan_digest: bundle.planDigest },
    plan_path: planPath,
    plan_digest: planDigest,
  });
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
  const ordered = [...refreshed].sort((left, right) => {
    const order = (action: PlanAction): number =>
      action.operation === "resolve" || action.operation === "reopen" ? 1 : 0;
    return order(left) - order(right);
  });
  const results: Json[] = [];
  for (const action of ordered) {
    results.push(await sendAction(current, action));
  }
  return { bundle: current, results };
}

export function editInEditor(body: string): string | null {
  const editor = process.env.EDITOR ?? process.env.VISUAL ?? "vi";
  const path = join(
    process.env.TMPDIR ?? "/tmp",
    `reviewmatic-body-${process.pid}-${Date.now()}.md`,
  );
  writeFileSync(path, body, { mode: 0o600 });
  const result = spawnSync(editor, [path], { stdio: "inherit", timeout: 600000 });
  if (result.error || result.status !== 0) {
    return null;
  }
  const edited = readFileSync(path, "utf8");
  return edited === body ? null : edited;
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
