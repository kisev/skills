import {
  WorkflowError,
  componentIsValid,
  gitRead,
  glabJson,
  isSha,
  nonemptyString,
  paginated,
  redact,
} from "./contract.js";

const IMPACTS = new Set(["major", "minor", "patch", "none", "not_applicable"]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return (
    Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key))
  );
}

function quoteBranch(value: string): string {
  let quoted = "";
  for (const character of value) {
    if (character.match(/[A-Za-z0-9_.~-]/) !== null) {
      quoted += character;
      continue;
    }
    for (const byte of Buffer.from(character, "utf8")) {
      quoted += `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
    }
  }
  return quoted;
}

export function evidenceIsValid(value: unknown): boolean {
  return (
    isObject(value) &&
    hasExactKeys(value, ["target_branch", "target_sha", "releases", "tags", "errors"]) &&
    (value.target_branch === null || nonemptyString(value.target_branch)) &&
    isSha(value.target_sha, true) &&
    componentIsValid(value.releases) &&
    componentIsValid(value.tags) &&
    Array.isArray(value.errors) &&
    (value.errors as unknown[]).every((item) => nonemptyString(item))
  );
}

export function collect(evidence: Record<string, unknown>): Record<string, unknown> {
  const project = evidence.project as Record<string, unknown>;
  const host = project.hostname as string;
  const projectId = project.id;
  const objectValue = evidence.object as Record<string, unknown>;
  const branch = Object.hasOwn(objectValue, "target_branch") ? objectValue.target_branch : null;
  const errors: string[] = [];
  let targetSha: unknown = null;
  if (nonemptyString(branch)) {
    try {
      const target = glabJson(
        host,
        `projects/${projectId}/repository/branches/${quoteBranch(branch as string)}`,
      );
      if (isObject(target) && isObject(target.commit)) {
        targetSha = (target.commit as Record<string, unknown>).id;
      }
      if (!isSha(targetSha)) {
        throw new WorkflowError("current target branch revision is unavailable");
      }
    } catch (error) {
      if (!(error instanceof WorkflowError)) throw error;
      errors.push(redact(error.message));
      targetSha = null;
    }
  } else {
    errors.push("target branch name is unavailable");
  }
  return {
    target_branch: nonemptyString(branch) ? branch : null,
    target_sha: targetSha,
    releases: paginated(host, `projects/${projectId}/releases`),
    tags: paginated(host, `projects/${projectId}/repository/tags`),
    errors: errors,
  };
}

export function assessmentIsValid(value: unknown): boolean {
  if (
    !isObject(value) ||
    !hasExactKeys(value, [
      "mode",
      "policy",
      "sources",
      "baseline",
      "target_branch",
      "target_sha",
      "fallback_reason",
      "release_impact",
      "release_rationale",
      "target_revision",
    ])
  ) {
    return false;
  }
  if (
    (value.mode !== "release" && value.mode !== "target_fallback") ||
    !nonemptyString(value.policy) ||
    !Array.isArray(value.sources) ||
    (value.sources as unknown[]).length === 0 ||
    !(value.sources as unknown[]).every((item) => nonemptyString(item)) ||
    !nonemptyString(value.target_branch) ||
    !isSha(value.target_sha) ||
    (value.target_revision !== "current" && value.target_revision !== "mr_snapshot")
  ) {
    return false;
  }
  if (value.mode === "target_fallback") {
    return (
      value.baseline === null &&
      nonemptyString(value.fallback_reason) &&
      value.release_impact === null &&
      value.release_rationale === null
    );
  }
  const baseline = value.baseline;
  return (
    value.fallback_reason === null &&
    value.target_revision === "current" &&
    typeof value.release_impact === "string" &&
    IMPACTS.has(value.release_impact) &&
    nonemptyString(value.release_rationale) &&
    isObject(baseline) &&
    hasExactKeys(baseline, ["name", "sha", "source"]) &&
    nonemptyString(baseline.name) &&
    isSha(baseline.sha) &&
    (baseline.source === "releases" || baseline.source === "tags")
  );
}

export function template(
  evidence: Record<string, unknown>,
  context: Record<string, unknown>,
): Record<string, unknown> {
  const release = context.release_evidence as Record<string, unknown>;
  const [targetSha, targetRevision] = comparisonTarget(evidence, context);
  const objectValue = evidence.object as Record<string, unknown>;
  const objectBranch = Object.hasOwn(objectValue, "target_branch") ? objectValue.target_branch : "";
  return {
    mode: "target_fallback",
    policy: "",
    sources: [],
    baseline: null,
    target_branch:
      release.target_branch === null || release.target_branch === ""
        ? objectBranch
        : release.target_branch,
    target_sha: targetSha,
    target_revision: targetRevision,
    fallback_reason: "",
    release_impact: null,
    release_rationale: null,
  };
}

function comparisonTarget(
  evidence: Record<string, unknown>,
  context: Record<string, unknown>,
): [string, string] {
  const release = context.release_evidence as Record<string, unknown>;
  const targetSha = release.target_sha;
  const exactGit = Object.hasOwn(context, "exact_git") ? context.exact_git : undefined;
  if (isSha(targetSha) && isObject(exactGit)) {
    const repoRoot = Object.hasOwn(exactGit, "repo_root") ? exactGit.repo_root : undefined;
    if (typeof repoRoot === "string") {
      try {
        const resolved = String(
          gitRead(repoRoot, ["rev-parse", "--verify", `${targetSha as string}^{commit}`]),
        ).trim();
        if (resolved === targetSha) {
          return [targetSha as string, "current"];
        }
      } catch (error) {
        if (!(error instanceof WorkflowError)) throw error;
      }
    }
  }
  return [evidence.start_sha as string, "mr_snapshot"];
}

export function validate(
  value: unknown,
  evidence: Record<string, unknown>,
  context: Record<string, unknown>,
): Record<string, unknown> {
  if (!assessmentIsValid(value)) {
    throw new WorkflowError(
      "SemVer assessment requires a release basis or explicit target fallback",
    );
  }
  const result = value as Record<string, unknown>;
  const release = context.release_evidence as Record<string, unknown>;
  const [expectedSha, expectedRevision] = comparisonTarget(evidence, context);
  if (
    result.target_branch !== release.target_branch ||
    result.target_sha !== expectedSha ||
    result.target_revision !== expectedRevision
  ) {
    throw new WorkflowError("SemVer target does not match collected target branch evidence");
  }
  if (result.mode === "target_fallback") {
    return result;
  }
  if (release.target_sha === null || expectedRevision !== "current") {
    throw new WorkflowError("release SemVer requires the current target branch revision");
  }
  const baseline = result.baseline as Record<string, unknown>;
  const catalog = release[baseline.source as string] as Record<string, unknown>;
  const nameField = baseline.source === "releases" ? "tag_name" : "name";
  const items = (catalog.items ?? []) as unknown[];
  if (
    catalog.complete !== true ||
    !items.some(
      (item) =>
        isObject(item) &&
        item[nameField] === baseline.name &&
        isObject(item.commit) &&
        (item.commit as Record<string, unknown>).id === baseline.sha &&
        item.upcoming_release !== true,
    )
  ) {
    throw new WorkflowError("SemVer baseline is not bound to a complete release/tag catalog");
  }
  const root = (context.exact_git as Record<string, unknown>).repo_root as string;
  for (const sha of [baseline.sha as string, result.target_sha as string]) {
    const resolved = String(gitRead(root, ["rev-parse", "--verify", `${sha}^{commit}`])).trim();
    if (resolved !== sha) {
      throw new WorkflowError("SemVer comparison commit is unavailable locally");
    }
  }
  gitRead(root, ["merge-base", baseline.sha as string, result.target_sha as string]);
  return result;
}

export function reportLines(content: Record<string, unknown>, locale: string): string[] {
  const assessment = content.semver_assessment as Record<string, unknown>;
  const ru = locale === "ru";

  const impactText = (value: string): string => {
    if (ru) {
      return { none: "нет", not_applicable: "не применимо" }[value] ?? value.toUpperCase();
    }
    return { none: "none", not_applicable: "not applicable" }[value] ?? value.toUpperCase();
  };

  const impact = impactText(content.semver_impact as string);
  const contribution = ru ? "Вклад MR / метка" : "MR contribution / label";
  const lines = [`- **${contribution}:** ${impact} - ${content.semver_rationale}`];
  const target = assessment.target_branch;
  if (assessment.mode === "release") {
    const baseline = (assessment.baseline as Record<string, unknown>).name;
    const basis = ru ? "База SemVer" : "SemVer basis";
    const releaseLabel = ru ? "Будущий релиз" : "Next release";
    const releaseImpact = impactText(assessment.release_impact as string);
    lines.push(
      `- **${basis}:** \`${baseline}\` → \`${target}\` + MR`,
      `- **${releaseLabel}:** ${releaseImpact} - ${assessment.release_rationale}`,
    );
  } else {
    const mode = ru
      ? "SemVer: fallback относительно целевой ветки"
      : "SemVer: target-branch fallback";
    lines.push(`- **${mode}:** \`${target}\` - ${assessment.fallback_reason}`);
    if (assessment.target_revision === "mr_snapshot") {
      lines.push(
        ru
          ? "- Текущая ревизия целевой ветки недоступна. Использован снимок базы MR."
          : "- Current target revision unavailable. Using the MR target snapshot.",
      );
    }
  }
  const policy = ru ? "Политика выпуска" : "Release policy";
  lines.push(`- **${policy}:** ${assessment.policy}`);
  return lines;
}
