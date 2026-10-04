import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  artifactEnvelope,
  artifactPayload,
  digest,
  isDict,
  readJson,
  regularFile,
  validateV2Artifact,
  WorkflowError,
  writeArtifact,
  writeJson,
} from "./contract.js";
import { expectedThreadBindings } from "./context.js";

type Json = Record<string, unknown>;

export const PACKAGE_POINTER_NAME = "context-package.json";
const ZERO_DIGEST = "0".repeat(64);
const VERDICTS = new Set(["confirmed", "refuted", "not_verified"]);
const PRIMARY_VERDICTS = new Set(["confirmed", "refuted", "unresolved"]);
const CLAIM_KINDS = new Set([
  "author_claim",
  "participant_opinion",
  "agreed_requirement",
  "accepted_risk",
  "confirmed_fact",
]);
const CANONICAL_FIELDS = [
  "mode",
  "binding",
  "goal",
  "acceptance_criteria",
  "claims",
  "constraints",
  "prior_decisions",
  "questions",
  "thread_registry",
  "supersedes",
] as const;

// The narrative background is intentionally excluded: editing it must never
// change the canonical facts of a recorded package.
export function canonicalPackageDigest(payload: Json): string {
  const value: Json = {};
  for (const key of CANONICAL_FIELDS) value[key] = payload[key] ?? null;
  return digest(value);
}

export function narrativePackageDigest(payload: Json): string {
  return digest(payload.background ?? "");
}

// The shared meaningful context every question and its results depend on.
// Binding fields and the narrative background are excluded: a new evidence
// snapshot or reworded background never invalidates collected results, while
// an edited question, claim, constraint, or agreed decision does.
function sharedContextInputs(payload: Json): Json {
  return {
    goal: payload.goal ?? null,
    acceptance_criteria: payload.acceptance_criteria ?? null,
    claims: payload.claims ?? [],
    constraints: payload.constraints ?? [],
    prior_decisions: payload.prior_decisions ?? [],
    thread_registry: payload.thread_registry ?? null,
  };
}

export function questionContextDigest(payload: Json): string {
  return digest({
    ...sharedContextInputs(payload),
    questions: payload.questions ?? [],
  });
}

// The version of the meaningful content one question and its answer depend on:
// the question itself plus the shared supporting context.
export function questionContextVersion(payload: Json, question: Json): string {
  const { context_digest: _declared, ...content } = question;
  return digest({
    ...sharedContextInputs(payload),
    question: content,
  });
}

export function questionContextVersions(payload: Json): Map<string, string> {
  const versions = new Map<string, string>();
  for (const question of (payload.questions ?? []) as Json[])
    versions.set(String(question.id), questionContextVersion(payload, question));
  return versions;
}

export function questionContextVersionList(payload: Json): Json {
  return Object.fromEntries(questionContextVersions(payload));
}

// Stamps every question of a package that is about to become an immutable
// artifact with its meaningful-context version. Answers and verifications copy
// this value, so a result produced against one package version can never be
// silently re-bound to a newer one. Already stamped questions must match.
export function bindQuestionContexts(payload: Json): void {
  for (const question of (payload.questions ?? []) as Json[]) {
    const expected = questionContextVersion(payload, question);
    if (question.context_digest !== undefined && question.context_digest !== expected)
      throw new WorkflowError(
        `context package question ${String(question.id)} context_digest does not match its ` +
          "meaningful context; remove manual bindings and let record-package stamp them",
      );
    question.context_digest = expected;
  }
}

// Verifies the stamps of an already recorded package. Unstamped questions are
// accepted only while the payload is still an unbound agent input; recorded
// artifacts always carry stamps.
function verifyQuestionContexts(payload: Json): void {
  const versions = questionContextVersions(payload);
  for (const question of (payload.questions ?? []) as Json[]) {
    if (question.context_digest === undefined) continue;
    const expected = versions.get(String(question.id));
    if (question.context_digest !== expected)
      throw new WorkflowError(
        `context package question ${String(question.id)} context_digest does not match its ` +
          `meaningful context (${expected}); re-record the package instead of editing bindings`,
      );
  }
}

function requireCurrentBinding(
  item: Json,
  versions: Map<string, string>,
  description: string,
): void {
  const id = String(item.question_id);
  const stored = item.context_digest;
  const expected = versions.get(id);
  if (typeof stored !== "string" || stored.length === 0)
    throw new WorkflowError(
      `${description} for question ${id} has no context binding; every result must copy the ` +
        "question context_digest of the recorded context package it was produced against, " +
        "so a result for older wording can never certify the current question",
    );
  if (stored !== expected)
    throw new WorkflowError(
      `${description} for question ${id} is bound to context digest ${stored}, but the ` +
        `recorded package's meaningful context for this question is ${expected}; collect a ` +
        "fresh result bound to the current package and keep this one as superseded history",
    );
}

export type SupersededResults = {
  entry: Json;
  questionIds: string[];
  answers: Json[];
  verifications: Json[];
};

// True when the result's binding names the meaningful-context version the
// package assigns to its question. Results without a binding are never
// current. Retirement must move exactly the entries this predicate rejects,
// never every result sharing the question ID.
export function isCurrentResult(item: Json, versions: Map<string, string>): boolean {
  return item.context_digest === versions.get(String(item.question_id));
}

// Compares the context version bound into each collected answer and
// verification with the version the new package assigns to its question.
// Results bound to another meaningful context — including results without a
// binding — no longer address the current questions; they move to the
// historical section instead of certifying the current package. Results bound
// to the current versions stay in place, so representation-only changes and
// unaffected questions keep their collected evidence.
export function extractSupersededResults(
  previous: { payload: Json; digest: string } | null,
  next: Json,
  answers: Json[],
  verifications: Json[],
): SupersededResults | null {
  const versions = questionContextVersions(next);
  const stale = (item: Json): boolean => !isCurrentResult(item, versions);
  const staleAnswers = answers.filter(stale);
  const staleVerifications = verifications.filter(stale);
  if (staleAnswers.length === 0 && staleVerifications.length === 0) return null;
  return {
    entry: {
      context_digest: previous === null ? ZERO_DIGEST : questionContextDigest(previous.payload),
      package_digest: previous === null ? ZERO_DIGEST : previous.digest,
      answers: staleAnswers,
      verifications: staleVerifications,
    },
    questionIds: [
      ...new Set([...staleAnswers, ...staleVerifications].map((item) => String(item.question_id))),
    ],
    answers: staleAnswers,
    verifications: staleVerifications,
  };
}

export function packagePointerPath(root: string): string {
  return join(root, PACKAGE_POINTER_NAME);
}

export function readPackagePointer(root: string): Json | null {
  const path = packagePointerPath(root);
  if (!existsSync(path)) return null;
  const pointer = readJson(regularFile(path, "context package pointer"), "context package pointer");
  return pointer;
}

export function recordedPackage(
  root: string,
): { path: string; digest: string; payload: Json } | null {
  const pointer = readPackagePointer(root);
  if (pointer === null) return null;
  const [, payload] = artifactPayload(String(pointer.package_path), "context_package");
  return {
    path: String(pointer.package_path),
    digest: String(pointer.package_digest),
    payload,
  };
}

export function threadRegistryFromContext(context: Json): Json[] {
  const bindings = expectedThreadBindings(context);
  return Object.entries(bindings).map(([id, binding]) => ({
    id,
    url: String(binding.url ?? ""),
    state: String(binding.state),
    summary: "",
    review_relevance: "",
  }));
}

export function localSectionDigests(bundle: Json): Json {
  const sections = bundle.sections as Json;
  return {
    committed: String((sections.committed as Json).sha256),
    staged: String((sections.staged as Json).sha256),
    unstaged: String((sections.unstaged as Json).sha256),
    untracked: digest(sections.untracked),
  };
}

function previousDecisionsFromLocalReport(previous: Json): Json[] {
  const task = previous.task as Json;
  const source = `previous finalized local report ${previous.evidence_digest as string}`;
  const decisions: Json[] = [];
  let index = 1;
  for (const item of (task.accepted_risks as string[]) ?? []) {
    decisions.push({ id: `prior-risk-${index}`, decision: String(item), source });
    index += 1;
  }
  index = 1;
  for (const item of (task.deferred as string[]) ?? []) {
    decisions.push({ id: `prior-deferred-${index}`, decision: String(item), source });
    index += 1;
  }
  return decisions;
}

function previousDecisionsFromContext(context: Json): Json[] {
  const incremental = context.incremental as Json | undefined;
  if (!isDict(incremental)) return [];
  const source = `previous finalized plan ${(incremental.incremental_baseline as Json)?.plan_digest ?? ""}`;
  return ((incremental.previous_thread_decisions as Json[]) ?? []).map((item) => ({
    id: `prior-thread-${String(item.id)
      .replace(/[^A-Za-z0-9._-]/g, "-")
      .slice(0, 48)}`,
    decision: `${item.outcome as string}: ${item.rationale as string}`,
    source: String(item.url ?? source),
  }));
}

// Mechanical skeletons. The agent formulates goal, claims, requirements,
// constraints, decisions and questions; the runtime only fixes bindings and
// registries so that nothing collected can be silently dropped.
export function packageTemplateForMr(evidence: Json, context: Json): Json {
  const exact = context.exact_git as Json;
  return {
    schema: "portable-gitlab/context-package/v2",
    mode: "mr",
    binding: {
      evidence_digest: "",
      artifact_root: String(evidence.artifact_root),
      repo_root: String(exact.repo_root),
      base_sha: String(evidence.base_sha),
      start_sha: String(evidence.start_sha),
      head_sha: String(evidence.head_sha),
      target_sha: evidence.target_sha == null ? null : String(evidence.target_sha),
      target_ref: evidence.target_ref == null ? null : String(evidence.target_ref),
    },
    goal: { status: "unknown" },
    acceptance_criteria: { status: "unknown", items: [] },
    background: "",
    claims: [],
    constraints: [],
    prior_decisions: previousDecisionsFromContext(context),
    questions: [],
    thread_registry: threadRegistryFromContext(context),
    supersedes: null,
    external_mutations: false,
  };
}

export function packageTemplateForLocal(
  bundle: Json,
  digestValue: string,
  previous: Json | null,
): Json {
  const task = previous === null ? null : (previous.task as Json);
  return {
    schema: "portable-gitlab/context-package/v2",
    mode: "local",
    binding: {
      evidence_digest: digestValue,
      artifact_root: String(bundle.artifact_root),
      repo_root: String(bundle.repo_root),
      base_sha: String(bundle.base_sha),
      head_sha: String(bundle.head_sha),
      ref: bundle.ref === null ? null : String(bundle.ref),
      sections: localSectionDigests(bundle),
    },
    goal:
      task === null
        ? { status: "unknown" }
        : { status: "unknown", text: String(task.goal ?? "") || undefined },
    acceptance_criteria:
      task === null
        ? { status: "unknown", items: [] }
        : { status: "unknown", items: [...((task.acceptance_criteria as string[]) ?? [])] },
    background: "",
    claims: [],
    constraints: task === null ? [] : [...((task.constraints as string[]) ?? [])],
    prior_decisions: previous === null ? [] : previousDecisionsFromLocalReport(previous),
    questions: [],
    supersedes: null,
    external_mutations: false,
  };
}

function requireText(value: unknown, field: string): void {
  if (typeof value !== "string" || value.length === 0)
    throw new WorkflowError(`context package ${field} must be a non-empty string`);
}

export function validateAnswers(
  answers: unknown,
  questionIds: Set<string>,
  versions: Map<string, string>,
  field: string,
): Json[] {
  if (!Array.isArray(answers)) throw new WorkflowError(`${field} must be an array`);
  const seen = new Set<string>();
  for (const [index, item] of answers.entries()) {
    const answer = item as Json;
    const where = `${field}[${index}]`;
    if (!isDict(answer)) throw new WorkflowError(`${where} must be an object`);
    requireText(answer.question_id, `${where}.question_id`);
    if (!questionIds.has(String(answer.question_id)))
      throw new WorkflowError(
        `${where}.question_id does not name a question of the recorded context package`,
      );
    if (!VERDICTS.has(String(answer.verdict)))
      throw new WorkflowError(`${where}.verdict must be confirmed, refuted, or not_verified`);
    if (String(answer.evidence ?? "").length === 0 && String(answer.reason ?? "").length === 0)
      throw new WorkflowError(
        `${where} requires evidence for confirmed/refuted or a concrete reason for not_verified`,
      );
    requireText(answer.run_id, `${where}.run_id`);
    requireText(answer.session_id, `${where}.session_id`);
    requireCurrentBinding(answer, versions, where);
    const key = `${String(answer.run_id)}:${String(answer.session_id)}:${String(answer.question_id)}`;
    if (seen.has(key))
      throw new WorkflowError(`${where} duplicates one answer for the same critic`);
    seen.add(key);
  }
  return answers as Json[];
}

export function validateVerifications(
  verifications: unknown,
  questionIds: Set<string>,
  versions: Map<string, string>,
  answers: Json[],
): Json[] {
  if (!Array.isArray(verifications)) throw new WorkflowError("verifications must be an array");
  const answerKey = (answer: Json): string =>
    `${answer.run_id ?? ""}:${answer.session_id ?? ""}:${answer.question_id}:${answer.verdict}`;
  const available = new Map(answers.map((answer) => [answerKey(answer), answer]));
  const covered = new Set<string>();
  for (const [index, item] of verifications.entries()) {
    const verification = item as Json;
    const where = `question_verifications[${index}]`;
    if (!isDict(verification)) throw new WorkflowError(`${where} must be an object`);
    requireText(verification.question_id, `${where}.question_id`);
    if (!questionIds.has(String(verification.question_id)))
      throw new WorkflowError(
        `${where}.question_id does not name a question of the recorded context package`,
      );
    requireCurrentBinding(verification, versions, where);
    const original = verification.original as Json;
    if (
      !isDict(original) ||
      typeof original.run_id !== "string" ||
      original.run_id.length === 0 ||
      typeof original.session_id !== "string" ||
      original.session_id.length === 0 ||
      !VERDICTS.has(String(original.verdict))
    )
      throw new WorkflowError(
        `${where}.original must name the preserved critic answer run, session, and verdict`,
      );
    if (!PRIMARY_VERDICTS.has(String(verification.verdict)))
      throw new WorkflowError(`${where}.verdict must be confirmed, refuted, or unresolved`);
    if (
      String(verification.evidence ?? "").length === 0 &&
      String(verification.reason ?? "").length === 0
    )
      throw new WorkflowError(
        `${where} requires evidence or an explicit reason; insufficient evidence stays visible`,
      );
    const key = answerKey({
      run_id: original.run_id,
      session_id: original.session_id,
      question_id: verification.question_id,
      verdict: original.verdict,
    });
    const answered = answers.some(
      (answer) => String(answer.question_id) === String(verification.question_id),
    );
    if (!available.has(key) && answered)
      throw new WorkflowError(
        `${where}.original does not match any retained critic answer; keep the original answer separately`,
      );
    const dedupe = `${original.run_id}:${original.session_id}:${String(verification.question_id)}`;
    if (covered.has(dedupe))
      throw new WorkflowError(`${where} verifies the same critic answer twice`);
    covered.add(dedupe);
  }
  return verifications as Json[];
}

// Answers collected from receipts or a local report, keyed per critic, for
// coverage checks. Assignments survive multiple critics: authorship stays on
// every answer and contradictions are reported, never merged away.
export function collectAnswers(sources: Json[]): { answers: Json[]; contradictions: string[] } {
  const answers: Json[] = [];
  for (const source of sources) {
    for (const answer of (source.question_answers as Json[]) ?? []) {
      answers.push({
        ...answer,
        run_id: answer.run_id ?? source.run_id,
        session_id: answer.session_id ?? source.session_id,
      });
    }
  }
  const byQuestion = new Map<string, Json[]>();
  for (const answer of answers) {
    const list = byQuestion.get(String(answer.question_id)) ?? [];
    list.push(answer);
    byQuestion.set(String(answer.question_id), list);
  }
  const contradictions: string[] = [];
  for (const [questionId, list] of byQuestion) {
    const verdicts = new Set(list.map((answer) => String(answer.verdict)));
    if (verdicts.has("confirmed") && verdicts.has("refuted")) contradictions.push(questionId);
  }
  return { answers, contradictions };
}

export function questionReport(questions: Json[], answers: Json[], verifications: Json[]): Json {
  const assigned = questions.filter((item) => item.critic === true);
  const assignedIds = new Set(assigned.map((item) => String(item.id)));
  const answered = new Set(answers.map((answer) => String(answer.question_id)));
  const answerKey = (answer: Json): string =>
    `${answer.run_id ?? ""}:${answer.session_id ?? ""}:${answer.question_id}`;
  const notVerified = new Set(
    answers.filter((answer) => answer.verdict === "not_verified").map(answerKey),
  );
  const verified = new Set(
    verifications
      .filter((item) => item.verdict !== "unresolved")
      .map((item) => String(item.question_id)),
  );
  // A not_verified critic answer stops counting as unverified exactly when a
  // primary verification preserved that original answer; a verification of a
  // different original never rescues it.
  const resolved = new Set(
    verifications
      .filter((item) => item.verdict !== "unresolved" && isDict(item.original))
      .map((item) => {
        const original = item.original as Json;
        return `${original.run_id ?? ""}:${original.session_id ?? ""}:${String(item.question_id)}`;
      }),
  );
  const unresolved = new Set(
    verifications
      .filter((item) => item.verdict === "unresolved")
      .map((item) => String(item.question_id)),
  );
  const byQuestion = new Map<string, Set<string>>();
  for (const answer of answers) {
    const verdicts = byQuestion.get(String(answer.question_id)) ?? new Set();
    verdicts.add(String(answer.verdict));
    byQuestion.set(String(answer.question_id), verdicts);
  }
  const contradictions = [...byQuestion.entries()].filter(
    ([, verdicts]) => verdicts.has("confirmed") && verdicts.has("refuted"),
  ).length;
  return {
    assigned: assigned.length,
    answered: [...answered].filter((id) => assignedIds.has(id)).length,
    unverified: [...notVerified].filter((key) => !resolved.has(key)).length,
    verified: verified.size,
    unresolved: unresolved.size,
    contradicted: contradictions,
  };
}

export function staleThreadIds(
  previousRegistry: Json[],
  previousBindings: Record<string, Json>,
  currentBindings: Record<string, Json>,
): string[] {
  return previousRegistry
    .filter((item) => {
      const binding = previousBindings[String(item.id)];
      const current = currentBindings[String(item.id)];
      if (binding === undefined || current === undefined) return true;
      return ["state", "url", "last_note_id", "last_note_body_sha256", "thread_sha256"].some(
        (key) => digest(binding[key] ?? null) !== digest(current[key] ?? null),
      );
    })
    .map((item) => String(item.id));
}

// Full structural and binding validation of an agent-authored package before
// it becomes an immutable artifact. No LLM call and no GitLab access happen
// here; completeness of threads is checked against the selected evidence.
export function validatePackagePayload(
  payload: Json,
  expected: {
    mode: "mr" | "local";
    evidenceDigest: string;
    artifactRoot: string;
    repoRoot: string;
    baseSha?: string;
    startSha?: string;
    headSha?: string;
    targetSha?: string | null;
    targetRef?: string | null;
    ref?: string | null;
    sections?: Json;
    bindings?: Record<string, Json>;
  },
): void {
  const envelope = artifactEnvelope("context_package", payload);
  validateV2Artifact(envelope, "context_package");
  if (payload.mode !== expected.mode)
    throw new WorkflowError("context package mode must match the selected review target");
  const binding = payload.binding as Json;
  if (binding.evidence_digest !== expected.evidenceDigest)
    throw new WorkflowError("context package does not bind the selected evidence digest");
  if (binding.artifact_root !== expected.artifactRoot)
    throw new WorkflowError("context package does not bind this review artifact root");
  if (binding.repo_root !== expected.repoRoot)
    throw new WorkflowError("context package repo_root does not match the selected checkout");
  if (expected.mode === "mr") {
    for (const [key, value] of [
      ["base_sha", expected.baseSha],
      ["start_sha", expected.startSha],
      ["head_sha", expected.headSha],
    ] as const)
      if (binding[key] !== value)
        throw new WorkflowError(`context package ${key} must match the exact reviewed revision`);
    if (expected.targetSha != null && binding.target_sha !== expected.targetSha)
      throw new WorkflowError("context package target_sha must match the exact target revision");
    if (binding.sections !== undefined)
      throw new WorkflowError("context package binding must not claim local sections in MR mode");
    const registry = payload.thread_registry as Json[];
    const expectedIds = new Set(Object.keys(expected.bindings ?? {}));
    const seen = new Set<string>();
    for (const item of registry) {
      const id = String(item.id);
      if (!expectedIds.has(id))
        throw new WorkflowError(
          `context package thread ${id} is not part of the collected evidence`,
        );
      if (seen.has(id))
        throw new WorkflowError(`context package thread registry repeats thread ${id}`);
      seen.add(id);
      requireText(item.summary, `thread_registry summary for ${id}`);
      requireText(item.review_relevance, `thread_registry review_relevance for ${id}`);
      const binding = (expected.bindings ?? {})[id];
      if (binding !== undefined && String(binding.state) !== String(item.state))
        throw new WorkflowError(
          `context package thread ${id} state must match the collected discussion state`,
        );
    }
    const missing = [...expectedIds].filter((id) => !seen.has(id));
    if (missing.length > 0)
      throw new WorkflowError(
        `context package thread registry is missing collected threads: ${missing.join(", ")}`,
      );
  } else {
    if (binding.ref !== (expected.ref ?? null))
      throw new WorkflowError(
        "context package comparison ref must equal the retained prepare-local boundary",
      );
    if (binding.head_sha !== expected.headSha)
      throw new WorkflowError("context package head_sha must match the prepared snapshot");
    const sections = binding.sections as Json | undefined;
    if (sections === undefined || expected.sections === undefined)
      throw new WorkflowError(
        "local context package must bind the committed/staged/unstaged/untracked sections",
      );
    for (const key of ["committed", "staged", "unstaged", "untracked"] as const)
      if (String(sections[key]) !== String((expected.sections as Json)[key]))
        throw new WorkflowError(
          `context package section ${key} does not match the prepared snapshot`,
        );
  }
  if ((payload.goal as Json).status === "known" && !requireGoalText(payload.goal as Json))
    throw new WorkflowError(
      "context package goal status known requires non-empty goal.text; keep status unknown when the task is unknown",
    );
  const acceptance = payload.acceptance_criteria as Json;
  if (
    acceptance.status === "known" &&
    (!Array.isArray(acceptance.items) || acceptance.items.length === 0)
  )
    throw new WorkflowError(
      "context package acceptance status known requires at least one criterion",
    );
  const claims = payload.claims as Json[];
  const claimIds = new Set(claims.map((item) => String(item.id)));
  if (claimIds.size !== claims.length)
    throw new WorkflowError("context package claim IDs must be unique");
  for (const claim of claims)
    for (const disputed of (claim.disputed_by as string[]) ?? [])
      if (!claimIds.has(disputed))
        throw new WorkflowError(
          `context package claim ${String(claim.id)} disputes unknown claim ${disputed}`,
        );
  const questionIds = new Set((payload.questions as Json[]).map((item) => String(item.id)));
  if (questionIds.size !== (payload.questions as Json[]).length)
    throw new WorkflowError("context package question IDs must be unique");
  verifyQuestionContexts(payload);
}

function requireGoalText(goal: Json): boolean {
  return typeof goal.text === "string" && goal.text.length > 0;
}

export async function writeContextPackage(root: string, payload: Json): Promise<[string, string]> {
  const [path, digestValue] = await writeArtifact(root, "context_package", payload);
  writeJson(packagePointerPath(root), {
    package_path: path,
    package_digest: digestValue,
    evidence_digest: String((payload.binding as Json).evidence_digest),
    canonical_digest: canonicalPackageDigest(payload),
    background_digest: narrativePackageDigest(payload),
  });
  return [path, digestValue];
}

export function supersedesDigest(root: string, supersedes: unknown): void {
  if (supersedes === null || supersedes === undefined) return;
  const pointer = readPackagePointer(root);
  const previousDigest = pointer === null ? null : String(pointer.package_digest ?? "");
  if (previousDigest !== supersedes)
    throw new WorkflowError(
      "context package supersedes must name the currently recorded package digest",
    );
}
