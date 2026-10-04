// Field-level schema diagnostics. This module is deliberately leaf-level: it
// imports nothing, so both the contract layer and the draft layer can use it
// without a dependency cycle. The canonical validator (a hand-written checker
// in contract.ts) is the oracle; this walker only locates and explains
// failures. contract.ts registers the oracle once at startup.

type Json = Record<string, unknown>;

export type DraftIssue = { path: string; message: string };

let validator: ((schema: Json, value: unknown, root: Json) => boolean) | null = null;

export function registerSchemaValidator(
  implementation: (schema: Json, value: unknown, root: Json) => boolean,
): void {
  validator = implementation;
}

function oracle(schema: Json, value: unknown, root: Json): boolean {
  if (validator === null)
    throw new Error(
      "schema diagnostics require the canonical validator; import contract.js before schemaIssues",
    );
  return validator(schema, value, root);
}

// Compact expectation text for diagnostics: names the type, required fields,
// and allowed values instead of dumping the schema document.
export function expectation(schema: Json): string {
  const parts: string[] = [];
  if (typeof schema.$ref === "string") return schema.$ref.slice("#/$defs/".length);
  if (typeof schema.const !== "undefined") parts.push(`exactly ${JSON.stringify(schema.const)}`);
  else if (Array.isArray(schema.enum))
    parts.push(`one of ${schema.enum.map((item) => JSON.stringify(item)).join(", ")}`);
  else if (Array.isArray(schema.type)) parts.push(schema.type.join(" or "));
  else if (typeof schema.type === "string") parts.push(schema.type);
  if (Array.isArray(schema.required) && schema.required.length > 0)
    parts.push(`with required fields ${schema.required.map((item) => String(item)).join(", ")}`);
  if (typeof schema.additionalProperties === "object" && isDict(schema.properties))
    parts.push(`with only the fields ${Object.keys(schema.properties).join(", ")}`);
  if (typeof schema.minLength === "number") parts.push(`non-empty`);
  if (typeof schema.minItems === "number") parts.push(`at least ${schema.minItems} items`);
  return parts.length > 0 ? parts.join("; ") : "a value matching the input schema";
}

// The canonical validator decides validity; this walker only locates and
// explains failures. `root` must be the schema document that $ref pointers
// resolve against.
export function schemaIssues(schema: Json, value: unknown, path: string, root: Json): DraftIssue[] {
  if (oracle(schema, value, root)) return [];
  if (typeof schema.$ref === "string") {
    const definition = (root.$defs as Json)[schema.$ref.slice("#/$defs/".length)];
    return isDict(definition)
      ? schemaIssues(definition, value, path, root)
      : [{ path, message: "Unknown schema reference" }];
  }
  const errors: DraftIssue[] = [];
  if (isDict(value)) {
    const properties = (schema.properties ?? {}) as Json;
    for (const key of (schema.required ?? []) as string[])
      if (!(key in value))
        errors.push({
          path: `${path}.${key}`,
          message: `Required field is missing; expected ${JSON.stringify(properties[key] ?? "the field declared by the input schema")}`,
        });
    for (const [key, item] of Object.entries(value)) {
      if (isDict(properties[key]))
        errors.push(...schemaIssues(properties[key], item, `${path}.${key}`, root));
      else if (schema.additionalProperties === false)
        errors.push({
          path: `${path}.${key}`,
          message: `Unknown field; allowed fields are ${Object.keys(properties).join(", ") || "none"}`,
        });
    }
  }
  if (Array.isArray(value) && isDict(schema.items))
    value.forEach((item, index) =>
      errors.push(...schemaIssues(schema.items as Json, item, `${path}[${index}]`, root)),
    );
  for (const branch of (schema.allOf ?? []) as Json[])
    errors.push(...schemaIssues(branch, value, path, root));
  if (isDict(schema.if)) {
    const branch = oracle(schema.if, value, root) ? schema.then : schema.else;
    if (isDict(branch)) errors.push(...schemaIssues(branch, value, path, root));
  }
  for (const keyword of ["anyOf", "oneOf"]) {
    const branches = schema[keyword];
    if (Array.isArray(branches) && !branches.some((branch) => oracle(branch, value, root))) {
      const alternatives = branches.map((branch) => schemaIssues(branch, value, path, root));
      const compatible = branches.filter(
        (branch) =>
          isDict(branch) &&
          (branch.type === undefined ||
            (branch.type === "object" && isDict(value)) ||
            (branch.type === "array" && Array.isArray(value)) ||
            branch.type === typeof value ||
            (branch.type === "null" && value === null)),
      );
      const candidates =
        compatible.length > 0
          ? compatible.map((branch) => schemaIssues(branch, value, path, root))
          : alternatives;
      candidates.sort((a, b) => a.length - b.length);
      errors.push(...candidates[0]);
    }
  }
  if (errors.length === 0)
    errors.push({
      path,
      message: `Expected ${expectation(schema)}`,
    });
  return errors;
}

function isDict(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
