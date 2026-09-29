import { WorkflowError, digest, labelSemantics, nonemptyString } from "./contract.js";

export interface LabelCatalogEntry {
  name: string;
  description: string | null;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return (
    Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key))
  );
}

function compareCodePoints(left: string, right: string): number {
  const first = Array.from(left);
  const second = Array.from(right);
  const length = Math.min(first.length, second.length);
  for (let index = 0; index < length; index += 1) {
    const delta = (first[index].codePointAt(0) ?? 0) - (second[index].codePointAt(0) ?? 0);
    if (delta !== 0) return delta;
  }
  return first.length - second.length;
}

function compareCasefold(left: string, right: string): number {
  const first = left.toLowerCase();
  const second = right.toLowerCase();
  const delta = compareCodePoints(first, second);
  if (delta !== 0) return delta;
  return compareCodePoints(left, right);
}

function sortedByCasefold(values: string[]): string[] {
  return [...values].sort((left, right) =>
    compareCodePoints(left.toLowerCase(), right.toLowerCase()),
  );
}

export function labelCatalog(evidence: Record<string, unknown>): LabelCatalogEntry[] {
  const component = evidence.labels;
  if (!isObject(component) || component.complete !== true) {
    throw new WorkflowError("project label catalog is incomplete");
  }
  const catalog: LabelCatalogEntry[] = [];
  const names = new Set<string>();
  const folded = new Set<string>();
  for (const value of (component.items ?? []) as unknown[]) {
    if (!isObject(value) || !nonemptyString(value.name)) {
      throw new WorkflowError("project label catalog entry is invalid");
    }
    const name = value.name as string;
    const description = Object.hasOwn(value, "description") ? value.description : null;
    if (description !== null && typeof description !== "string") {
      throw new WorkflowError("project label description is invalid");
    }
    if (names.has(name) || folded.has(name.toLowerCase())) {
      throw new WorkflowError("project label catalog contains duplicate names");
    }
    names.add(name);
    folded.add(name.toLowerCase());
    catalog.push({ name: name, description: description as string | null });
  }
  return catalog.sort((left, right) => compareCasefold(left.name, right.name));
}

export function validateLabelAssessments(
  evidence: Record<string, unknown>,
  value: unknown,
  semverImpact: string,
): Record<string, unknown> {
  const catalog = labelCatalog(evidence);
  const catalogByName = new Map(catalog.map((item) => [item.name, item]));
  if (!Array.isArray(value)) {
    throw new WorkflowError("label assessments must be an array");
  }
  const assessments = new Map<string, Record<string, unknown>>();
  for (const item of value) {
    if (
      !isObject(item) ||
      !hasExactKeys(item, ["name", "status", "rationale"]) ||
      !nonemptyString(item.name) ||
      (item.status !== "applicable" &&
        item.status !== "inapplicable" &&
        item.status !== "unresolved") ||
      !nonemptyString(item.rationale) ||
      assessments.has(item.name as string)
    ) {
      throw new WorkflowError("label assessment is invalid");
    }
    assessments.set(item.name as string, item);
  }
  if (
    assessments.size !== catalogByName.size ||
    ![...catalogByName.keys()].every((name) => assessments.has(name))
  ) {
    throw new WorkflowError("label assessments must cover the complete project catalog");
  }
  const compatibility: Record<string, string[]> = { major: [], minor: [], patch: [] };
  const labelItems = ((evidence.labels as Record<string, unknown>).items ?? []) as unknown[];
  for (const item of labelItems) {
    const semantics = labelSemantics(item);
    if (semantics !== null && semantics[0] === "compatibility") {
      compatibility[semantics[1]].push((item as Record<string, unknown>).name as string);
    }
  }
  let selected: string | null = null;
  if (Object.hasOwn(compatibility, semverImpact)) {
    const candidates = sortedByCasefold(compatibility[semverImpact]);
    if (candidates.length === 1) {
      selected = candidates[0] as string;
      if ((assessments.get(selected) as Record<string, unknown>).status !== "applicable") {
        throw new WorkflowError("SemVer impact requires the matching compatibility label");
      }
    } else if (
      candidates.length > 1 &&
      candidates.some(
        (name) => (assessments.get(name) as Record<string, unknown>).status !== "unresolved",
      )
    ) {
      throw new WorkflowError("ambiguous SemVer compatibility labels must remain unresolved");
    }
    for (const [impact, names] of Object.entries(compatibility)) {
      if (
        impact !== semverImpact &&
        names.some(
          (name) => (assessments.get(name) as Record<string, unknown>).status === "applicable",
        )
      ) {
        throw new WorkflowError("an incompatible SemVer label cannot be assessed as applicable");
      }
    }
  }
  const objectValue = evidence.object;
  const currentValue = isObject(objectValue)
    ? Object.hasOwn(objectValue, "labels")
      ? objectValue.labels
      : null
    : null;
  if (!Array.isArray(currentValue) || !currentValue.every((item) => typeof item === "string")) {
    throw new WorkflowError("current MR labels are unavailable");
  }
  const currentRaw = currentValue as string[];
  const current = sortedByCasefold([...new Set(currentRaw)]);
  if (current.length !== currentRaw.length || !current.every((name) => catalogByName.has(name))) {
    throw new WorkflowError("current MR labels do not match the complete catalog");
  }
  const entries: Record<string, unknown>[] = catalog.map((item) => ({
    ...(assessments.get(item.name) as Record<string, unknown>),
    description: item.description,
    current: current.includes(item.name),
  }));
  const add = sortedByCasefold(
    entries
      .filter((item) => item.status === "applicable" && !current.includes(item.name as string))
      .map((item) => item.name as string),
  );
  const remove = sortedByCasefold(
    entries
      .filter((item) => item.status === "inapplicable" && current.includes(item.name as string))
      .map((item) => item.name as string),
  );
  const removeSet = new Set(remove);
  const proposed = sortedByCasefold([
    ...new Set([...current.filter((name) => !removeSet.has(name)), ...add]),
  ]);
  return {
    complete: true,
    catalog_sha256: digest(catalog),
    catalog: catalog,
    assessments: entries,
    current: current,
    add: add,
    remove: remove,
    proposed: proposed,
    unresolved: entries
      .filter((item) => item.status === "unresolved")
      .map((item) => item.name as string),
    semver: {
      impact: semverImpact,
      candidates: sortedByCasefold(compatibility[semverImpact] ?? []),
      selected: selected,
    },
  };
}
