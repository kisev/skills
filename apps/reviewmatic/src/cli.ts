#!/usr/bin/env node
import {
  artifactPayload,
  artifactRoot,
  capabilities,
  collect,
  error as contractError,
  emit,
  finalizePayload,
  parseTarget,
  redact,
  writeArtifact,
  writeJson,
  WorkflowError,
} from "./contract.js";
import {
  emptyScopeReason,
  finalizeLocal,
  localBundle,
  persistLocalDraft,
  prepareFollowup,
  recordLocalInput,
  recordLocalPackage,
  recordReview,
  selectLocalDraft,
} from "./local-review.js";
import { localScope, scopeForRoot } from "./scope.js";
import { markerRun, StateArtifactError } from "./state-artifacts.js";
import { VERSION } from "./version.js";
import { dispatch, prepared, type WorkflowArguments } from "./workflow.js";
import { discoverArtifactRoot, loadPlan, planItems } from "./tui/support.js";
import { runTui } from "./tui/app.js";
import { stringsFor } from "./tui/strings.js";
import { registrySummary } from "./worktree.js";
import {
  startReview,
  resumeReview,
  checkReview,
  finishReview,
  recordDraftCritic,
  recordDraftInput,
  recordDraftPackage,
  repairReview,
  refreshReview,
} from "./draft.js";
import {
  program,
  common,
  fail,
  Option,
  applyConfig,
  configFile,
  reporter,
  type Command,
} from "./generated/cli.js";

type Fields = Record<string, unknown>;
type Json = Record<string, unknown>;

interface OptionSpec {
  name: string;
  description: string;
  required?: boolean;
  default?: string;
  choices?: string[];
  flag?: boolean;
  collect?: boolean;
}

interface CommandSpec {
  signature: string;
  description: string;
  options: OptionSpec[];
}

const definitions: CommandSpec[] = [
  {
    signature: "repair-review",
    description: "Open an existing new plan for targeted local repair",
    options: [
      { name: "artifact-root", description: "artifact root", required: true },
      {
        name: "kind",
        description: "repair scope",
        choices: ["presentation", "fix", "decision"],
        default: "presentation",
      },
    ],
  },
  {
    signature: "refresh-review",
    description: "Refresh changed evidence while retaining draft findings and decisions",
    options: [{ name: "draft", description: "existing review draft", required: true }],
  },
  {
    signature: "start-review",
    description: "Collect evidence and context once and create one editable review draft",
    options: [
      { name: "url", description: "exact HTTPS GitLab merge request URL", required: true },
      {
        name: "repo-root",
        description: "local checkout root; defaults to the current repository",
      },
      {
        name: "review-mode",
        description: "review depth",
        default: "normal",
        choices: ["fast", "normal", "deep"],
      },
      { name: "locale", description: "response language", default: "en", choices: ["en", "ru"] },
      {
        name: "incremental",
        description: "incremental baseline policy",
        default: "auto",
        choices: ["auto", "off"],
      },
    ],
  },
  {
    signature: "resume-review",
    description: "Recover the selected editable draft without recollecting GitLab",
    options: [{ name: "artifact-root", description: "artifact root", required: true }],
  },
  {
    signature: "check-review",
    description: "Validate the entire draft locally without committing review state",
    options: [{ name: "draft", description: "generated editable review draft", required: true }],
  },
  {
    signature: "finish-review",
    description: "Revalidate freshness once and finalize the complete review atomically",
    options: [{ name: "draft", description: "generated editable review draft", required: true }],
  },
  {
    signature: "prepare",
    description: "Collect GET-only GitLab evidence and initialize review progress",
    options: [
      { name: "url", description: "exact HTTPS GitLab merge request URL", collect: true },
      { name: "project-url", description: "exact HTTPS GitLab project URL" },
      { name: "repo-root", description: "local checkout root" },
      {
        name: "review-mode",
        description: "review depth",
        default: "normal",
        choices: ["fast", "normal", "deep"],
      },
      { name: "locale", description: "response language", default: "en", choices: ["en", "ru"] },
      {
        name: "incremental",
        description: "incremental baseline policy",
        default: "auto",
        choices: ["auto", "off"],
      },
    ],
  },
  {
    signature: "context",
    description: "Collect the review context for selected evidence",
    options: [
      { name: "evidence", description: "evidence snapshot path", required: true },
      { name: "repo-root", description: "local checkout root", required: true },
      {
        name: "incremental",
        description: "incremental baseline policy",
        default: "auto",
        choices: ["auto", "off"],
      },
      {
        name: "review-mode",
        description: "review depth",
        default: "normal",
        choices: ["fast", "normal", "deep"],
      },
      { name: "locale", description: "response language", default: "en", choices: ["en", "ru"] },
    ],
  },
  {
    signature: "scaffold-review",
    description: "Scaffold the immutable review plan",
    options: [
      { name: "evidence", description: "evidence snapshot path", required: true },
      { name: "context", description: "review context path", required: true },
      { name: "decision", description: "review decision path", required: true },
      { name: "content", description: "plan content file", required: true },
    ],
  },
  {
    signature: "status",
    description: "Print the current review status",
    options: [{ name: "artifact-root", description: "artifact root", required: true }],
  },
  {
    signature: "next",
    description: "Print the current review status and next action",
    options: [{ name: "artifact-root", description: "artifact root", required: true }],
  },
  {
    signature: "template-review",
    description: "Emit a review template for the current stage",
    options: [
      { name: "artifact-root", description: "artifact root", required: true },
      {
        name: "kind",
        description: "template kind",
        required: true,
        choices: ["critic", "decision", "content"],
      },
    ],
  },
  {
    signature: "report-review",
    description: "Revalidate and report the finished review",
    options: [{ name: "artifact-root", description: "artifact root", required: true }],
  },
  {
    signature: "finalize",
    description: "Recheck evidence freshness and record the finalize report",
    options: [
      { name: "artifact-root", description: "artifact root", required: true },
      { name: "report", description: "readiness report path" },
    ],
  },
  {
    signature: "record-package",
    description: "Record the agent-authored context package bound to selected evidence",
    options: [
      { name: "draft", description: "generated editable review draft (remote MR mode)" },
      { name: "bundle", description: "local WIP snapshot path (local mode)" },
      { name: "input", description: "completed context package input", required: true },
    ],
  },
  {
    signature: "record-input",
    description:
      "Apply semantic review sections to the prepared draft, preserving machine bindings",
    options: [
      { name: "draft", description: "generated editable review draft (remote MR mode)" },
      { name: "bundle", description: "local WIP snapshot path (local mode)" },
      { name: "input", description: "semantic sections input file", required: true },
    ],
  },
  {
    signature: "record-critic",
    description: "Import one independent critic receipt into the draft verbatim",
    options: [
      { name: "draft", description: "generated editable review draft", required: true },
      { name: "input", description: "critic receipt response file", required: true },
    ],
  },
  {
    signature: "scope-review",
    description: "Print the prepared review scope overview from recorded evidence",
    options: [{ name: "artifact-root", description: "artifact root", required: true }],
  },
  {
    signature: "prepare-local",
    description: "Collect local WIP evidence: staged, unstaged, and untracked",
    options: [
      { name: "repo-root", description: "local checkout root", required: true },
      {
        name: "ref",
        description:
          "explicit local comparison revision; adds its commits since the merge base with HEAD",
      },
      {
        name: "incremental",
        description: "incremental baseline policy",
        default: "auto",
        choices: ["auto", "off"],
      },
    ],
  },
  {
    signature: "finalize-local",
    description: "Check local WIP evidence freshness",
    options: [
      { name: "bundle", description: "local WIP snapshot path", required: true },
      { name: "report", description: "local review draft path" },
    ],
  },
  {
    signature: "assess-mode",
    description: "Check whether a review mode is supported",
    options: [
      {
        name: "mode",
        description: "requested review mode",
        required: true,
        choices: ["fast", "normal", "deep"],
      },
      { name: "critic-available", description: "an independent critic is available", flag: true },
    ],
  },
  {
    signature: "finalize-review",
    description: "Verify the finalized review decision without external mutations",
    options: [
      { name: "evidence", description: "evidence snapshot path", required: true },
      { name: "report", description: "review decision path", required: true },
      {
        name: "mode",
        description: "review mode",
        required: true,
        choices: ["fast", "normal", "deep", "incremental", "unchanged"],
      },
      { name: "critic-receipt", description: "critic receipt path" },
      { name: "finalize-report", description: "finalize report path", required: true },
      { name: "context", description: "review context path", required: true },
    ],
  },
  {
    signature: "record-artifact",
    description: "Record a private schema-valid review artifact",
    options: [
      {
        name: "kind",
        description: "artifact kind",
        required: true,
        choices: ["analysis_report", "critic_receipt", "release_readiness"],
      },
      { name: "evidence", description: "evidence snapshot path", required: true },
      { name: "input", description: "artifact input path", required: true },
    ],
  },
  {
    signature: "plan",
    description: "Open the finalized review plan in the experimental TUI",
    options: [
      {
        name: "artifact-root",
        description: "artifact root; discovered automatically when omitted",
      },
      { name: "print", description: "print the plan overview without a terminal UI", flag: true },
    ],
  },
  {
    signature: "worktree list",
    description: "List review worktrees recorded by local patch application",
    options: [],
  },
  {
    signature: "publication [mode]",
    description: "Historical guarded actions are no longer executable",
    options: [
      { name: "action", description: "publication action path" },
      { name: "confirm", description: "action SHA-256 digest" },
    ],
  },
  {
    signature: "capabilities",
    description: "Print machine capabilities JSON",
    options: [],
  },
  {
    signature: "marker-run [mutation...]",
    description: "Run a mutation and record its post-success marker",
    options: [],
  },
];

const cli = common(
  program("reviewmatic", "Interactive terminal companion for GitLab code reviews", VERSION),
  "REVIEWMATIC",
).option("--capabilities", "print machine capabilities JSON and exit");

function workflowArguments(command: string, fields: Fields): WorkflowArguments {
  return {
    command,
    artifactRoot: fields.artifactRoot as string | undefined,
    evidence: fields.evidence as string | undefined,
    repoRoot: fields.repoRoot as string | null | undefined,
    incremental: fields.incremental as string | undefined,
    reviewMode: fields.reviewMode as string | undefined,
    locale: fields.locale as string | undefined,
    kind: fields.kind as string | undefined,
    input: fields.input as string | undefined,
    report: fields.report as string | undefined,
    criticReceipt: (fields.criticReceipt as string | undefined) ?? null,
    finalizeReport: fields.finalizeReport as string | undefined,
    context: fields.context as string | undefined,
    mode: fields.mode as string | undefined,
    decision: fields.decision as string | undefined,
    content: fields.content as string | undefined,
  };
}

async function runPrepare(fields: Fields): Promise<void> {
  const urls = (fields.url as string[] | undefined) ?? [];
  const projectUrl = fields.projectUrl as string | undefined;
  if (urls.length > 0 === Boolean(projectUrl)) {
    throw new WorkflowError("provide exact --url target or --project-url, but not both");
  }
  if (projectUrl !== undefined) {
    throw new WorkflowError("project creation mode is only available for task preparation");
  }
  if (urls.length !== 1) {
    throw new WorkflowError("code-review accepts exactly one --url target");
  }
  const target = parseTarget(urls[0], new Set(["merge_requests"]));
  const results: Json[] = [];
  try {
    const bundle = await collect(target, "code-review", {
      locale: (fields.locale as string) ?? "en",
    });
    const item: Json = {
      target: target.url,
      status: "ok",
      artifact_path: bundle.preview_artifact_path,
      digest: bundle.preview_digest,
      artifact_root: bundle.artifact_root,
      head_sha: bundle.head_sha,
      base_sha: bundle.base_sha ?? null,
      start_sha: bundle.start_sha ?? null,
      complete: bundle.retrieval_complete,
      components_complete: bundle.components_complete,
    };
    Object.assign(
      item,
      await prepared(
        {
          command: "prepare",
          repoRoot: fields.repoRoot as string | null | undefined,
          reviewMode: (fields.reviewMode as string) ?? "normal",
          locale: (fields.locale as string) ?? "en",
          incremental: (fields.incremental as string) ?? "auto",
        },
        bundle,
      ),
    );
    results.push(item);
  } catch (caught) {
    if (!(caught instanceof WorkflowError)) throw caught;
    process.stderr.write(`${redact(caught.message)}\n`);
    results.push({ target: target.url, status: "error", error: redact(caught.message) });
  }
  const status = results.every((item) => item.status === "ok") ? "ok" : "partial";
  emit({
    status: status,
    summary: {
      tldr: "Completed GET-only GitLab evidence preparation.",
      scope: results.map((item) => item.target),
      risks: status !== "ok" ? ["one or more targets failed"] : [],
      checks: [
        "exact target identity",
        "endpoint allowlist",
        "pagination completeness",
        "exact SHA",
      ],
    },
    items: results,
    external_mutations: false,
  });
  process.exitCode = status === "ok" ? 0 : 1;
}

async function runPrepareLocal(fields: Fields): Promise<void> {
  const bundle = await localBundle(
    String(fields.repoRoot),
    "code-review",
    (fields.ref as string | undefined) ?? null,
  );
  const sections = bundle.sections as Record<string, Record<string, unknown>>;
  const empty = emptyScopeReason(bundle);
  if (empty !== null) {
    emit({
      status: "empty_scope",
      reason: empty,
      summary: {
        tldr: "No reviewable local scope exists at the selected boundary.",
        scope: [String(bundle.repo_root)],
        risks: [],
        checks: ["HEAD", "staged", "unstaged", "non-ignored untracked", "merge base"],
      },
      head_sha: bundle.head_sha,
      base_sha: bundle.base_sha,
      ref: bundle.ref,
      complete: bundle.retrieval_complete,
      external_mutations: false,
    });
    process.exitCode = 2;
    return;
  }
  const root = await artifactRoot(String(bundle.artifact_root));
  const [path, digestValue] = await writeArtifact(root, "local_wip_snapshot", bundle);
  const incremental = (fields.incremental as string) ?? "auto";
  const review = prepareFollowup(root, bundle, digestValue, incremental);
  // Materialize the draft for this snapshot at preparation time: an existing
  // draft bound to the same evidence survives untouched, while a missing or
  // stale draft is rebuilt from the current snapshot and baseline.
  const draftSelection = selectLocalDraft(root, bundle, digestValue, incremental);
  if (draftSelection.materialized)
    persistLocalDraft(root, digestValue, draftSelection, draftSelection.draft);
  writeJson(`${root}/current-local.json`, {
    evidence_path: path,
    evidence_digest: digestValue,
  });
  const complete = bundle.retrieval_complete === true;
  emit({
    status: complete ? "ok" : "incomplete",
    summary: {
      tldr: "Collected local WIP evidence: staged, unstaged, and untracked.",
      scope: [String(bundle.repo_root)],
      risks: complete ? [] : ["local evidence incomplete"],
      checks: ["HEAD", "staged", "unstaged", "non-ignored untracked", "symlink/binary/size"],
    },
    bundle: path,
    artifact_path: path,
    digest: digestValue,
    head_sha: bundle.head_sha,
    base_sha: bundle.base_sha,
    ref: bundle.ref,
    scope: {
      committed: (sections.committed.diff as string).length > 0,
      staged: (sections.staged.diff as string).length > 0,
      unstaged: (sections.unstaged.diff as string).length > 0,
      untracked_files: (sections.untracked.items as Record<string, unknown>[]).length,
    },
    scope_overview: localScope(bundle, review, String(path)),
    complete: bundle.retrieval_complete,
    review: review,
    external_mutations: false,
  });
  process.exitCode = complete ? 0 : 2;
}

async function runRecordPackage(fields: Fields): Promise<void> {
  const hasDraft = fields.draft !== undefined;
  const hasBundle = fields.bundle !== undefined;
  if (hasDraft === hasBundle) {
    throw new WorkflowError(
      "record-package requires exactly one target: --draft for a remote MR review or --bundle for a local review",
    );
  }
  if (hasDraft) {
    emit(await recordDraftPackage(String(fields.draft), String(fields.input)));
    return;
  }
  emit(await recordLocalPackage(String(fields.bundle), String(fields.input)));
}

async function runRecordInput(fields: Fields): Promise<void> {
  const hasDraft = fields.draft !== undefined;
  const hasBundle = fields.bundle !== undefined;
  if (hasDraft === hasBundle) {
    throw new WorkflowError(
      "record-input requires exactly one target: --draft for a remote MR review or --bundle for a local review",
    );
  }
  let result: Json;
  if (hasDraft) result = await recordDraftInput(String(fields.draft), String(fields.input));
  else result = await recordLocalInput(String(fields.bundle), String(fields.input));
  emit(result);
  process.exitCode = result.status === "ok" ? 0 : 2;
}

async function runRecordCritic(fields: Fields): Promise<void> {
  const result = await recordDraftCritic(String(fields.draft), String(fields.input));
  emit(result);
  process.exitCode = result.status === "ok" ? 0 : 2;
}

async function runScopeReview(fields: Fields): Promise<void> {
  emit({
    status: "ok",
    scope: scopeForRoot(String(fields.artifactRoot)),
    external_mutations: false,
  });
}

async function runFinalizeLocal(fields: Fields): Promise<void> {
  let result = await finalizeLocal(String(fields.bundle));
  const [, bundle] = artifactPayload(String(fields.bundle), "local_wip_snapshot");
  const root = await artifactRoot(String(bundle.artifact_root));
  result = finalizePayload(result, String(fields.bundle), bundle, "local_wip_snapshot");
  const [path, digestValue] = await writeArtifact(root, "finalize_report", result);
  let reviewResult: Record<string, unknown> | null = null;
  if (fields.report !== undefined && result.status === "ok") {
    reviewResult = await recordReview(root, String(fields.bundle), String(fields.report));
  }
  emit({
    status: result.status,
    summary: {
      tldr: "Checked local WIP evidence freshness.",
      scope: [String(bundle.repo_root)],
      risks: (result.changed as string[] | undefined) ?? [],
      checks: ["HEAD", "all WIP sections"],
    },
    artifact_path: path,
    digest: digestValue,
    result: result,
    review: reviewResult,
    external_mutations: false,
  });
  process.exitCode = result.status === "ok" ? 0 : 2;
}

function runAssessMode(fields: Fields): void {
  const mode = fields.mode as string;
  if (["normal", "deep"].includes(mode) && fields.criticAvailable !== true) {
    emit({
      status: "unsupported",
      reason: "independent critic receipt is required",
      details: { mode: mode },
    });
    process.exitCode = 4;
    return;
  }
  emit({
    status: "ok",
    mode: mode,
    independent_critic_required: ["normal", "deep"].includes(mode),
  });
  process.exitCode = 0;
}

async function runPublication(args: string[], fields: Fields): Promise<void> {
  void args;
  void fields;
  emit({
    status: "blocked",
    error:
      "Legacy guarded actions are historical only; prepare a new runbook with direct glab commands",
    external_mutations: false,
  });
  process.exitCode = 2;
}

async function runPlan(fields: Fields): Promise<void> {
  const root = (fields.artifactRoot as string | undefined) ?? discoverArtifactRoot();
  if (root === null) {
    throw new WorkflowError("no finalized review plan was found; run a review first");
  }
  const bundle = loadPlan(root);
  if (fields.print === true || process.stdout.isTTY !== true || process.stdin.isTTY !== true) {
    const strings = stringsFor(bundle.plan.locale as string | undefined);
    const items = planItems(bundle);
    const lines = [
      `${strings.title}: ${String(bundle.plan.verdict ?? "?")}`,
      `${strings.target}: ${String((bundle.plan.target as Json | undefined)?.url ?? "")}`,
      "",
      ...items.map(
        (item) =>
          `- (${item.kind}) ${item.path !== null ? `${item.path}${item.line !== null ? `:${item.line}` : ""} ` : ""}${item.title}`,
      ),
    ];
    process.stdout.write(`${lines.join("\n")}\n`);
    process.exitCode = 0;
    return;
  }
  process.exitCode = await runTui(bundle);
}

async function runCommand(command: string, args: string[], fields: Fields): Promise<void> {
  if (command === "publication" && process.argv.slice(3).includes("--capabilities")) {
    emit({
      operations: [],
      publication: "manual glab commands",
      external_mutations: false,
    });
    return;
  }
  if (cli.opts().capabilities === true || command === "capabilities") {
    process.exitCode = capabilities("code-review");
    return;
  }
  if (command === "publication") {
    await runPublication(args, fields);
    return;
  }
  if (command === "plan") {
    try {
      await runPlan(fields);
    } catch (caught) {
      if (!(caught instanceof WorkflowError)) throw caught;
      process.exitCode = contractError("invalid_input", caught.message, 2);
    }
    return;
  }
  if (command === "worktree" && args[0] === "list") {
    emit({
      status: "ok",
      items: registrySummary().map((record) => ({
        path: record.path,
        branch: record.branch,
        head_sha: record.head_sha,
        mr_url: record.mr_url,
        created_at: record.created_at,
        commit_sha: record.commit_sha,
        pushed: record.pushed,
      })),
      external_mutations: false,
    });
    return;
  }
  try {
    if (command === "repair-review" || command === "refresh-review") {
      const result =
        command === "repair-review"
          ? await repairReview(String(fields.artifactRoot), String(fields.kind))
          : await refreshReview(String(fields.draft));
      emit(result);
      process.exitCode = ["ok", "needs_reassessment"].includes(String(result.status)) ? 0 : 2;
      return;
    }
    if (["start-review", "resume-review", "check-review", "finish-review"].includes(command)) {
      const result =
        command === "start-review"
          ? await startReview({
              url: String(fields.url),
              repoRoot: fields.repoRoot as string | undefined,
              reviewMode: fields.reviewMode as string,
              locale: fields.locale as string,
              incremental: fields.incremental as string,
            })
          : command === "resume-review"
            ? await resumeReview(String(fields.artifactRoot))
            : command === "check-review"
              ? await checkReview(String(fields.draft))
              : await finishReview(String(fields.draft));
      emit(result);
      process.exitCode = result.status === "ok" ? 0 : 2;
      return;
    }
    const code = await dispatch(workflowArguments(command, fields));
    if (code !== null) {
      process.exitCode = code;
      return;
    }
    if (command === "prepare") await runPrepare(fields);
    else if (command === "prepare-local") await runPrepareLocal(fields);
    else if (command === "record-package") await runRecordPackage(fields);
    else if (command === "record-input") await runRecordInput(fields);
    else if (command === "record-critic") await runRecordCritic(fields);
    else if (command === "scope-review") await runScopeReview(fields);
    else if (command === "finalize-local") await runFinalizeLocal(fields);
    else if (command === "assess-mode") runAssessMode(fields);
    else process.exitCode = contractError("invalid_command", "a supported subcommand is required");
  } catch (caught) {
    if (!(caught instanceof WorkflowError)) throw caught;
    const code = caught.message.includes("unavailable") ? "tool_unavailable" : "invalid_input";
    process.exitCode = contractError(code, caught.message, code === "tool_unavailable" ? 3 : 2);
  }
}

for (const spec of definitions) {
  const command = cli.command(spec.signature).description(spec.description);
  for (const option of spec.options) {
    const instance = new Option(
      `--${option.name}${option.flag ? "" : " <value>"}`,
      option.description,
    );
    if (option.choices !== undefined) instance.choices(option.choices);
    if (option.default !== undefined) instance.default(option.default);
    if (option.required === true) instance.makeOptionMandatory();
    if (option.collect === true) {
      instance.argParser((value: string, previous: string[] = []) => [...previous, value]);
    }
    command.addOption(instance);
  }
  command.action(async (...values: unknown[]) => {
    const cmd = values.at(-1) as Command;
    const config = await configFile(cli.opts().config);
    applyConfig(cli, config);
    applyConfig(cmd, config);
    const fields: Fields = { ...cmd.optsWithGlobals() };
    const logs = reporter(fields);
    try {
      logs.emit({ phase: cmd.name(), message: "Executing command", level: "debug" });
      await runCommand(cmd.name(), cmd.args, fields);
      logs.emit({ phase: `${cmd.name()}.done`, message: "Command complete", level: "debug" });
    } finally {
      logs.close();
    }
  });
}

cli.action(() => {
  if (cli.opts().capabilities === true) {
    process.exitCode = capabilities("code-review");
    return;
  }
  process.exitCode = contractError("invalid_command", "a supported subcommand is required");
});

try {
  if (process.argv.length === 2) {
    if (process.stdout.isTTY === true) {
      await runPlan({});
    } else {
      cli.outputHelp();
    }
  } else if (process.argv[2] === "marker-run") {
    process.exitCode = await markerRun(process.argv.slice(3));
  } else await cli.parseAsync(process.argv);
} catch (caught) {
  if (caught instanceof StateArtifactError) {
    process.stderr.write(`error: ${caught.message}\n`);
    process.exitCode = 2;
  } else {
    fail("reviewmatic", caught, process.argv.includes("--json"));
  }
}
