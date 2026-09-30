// JSONC support: tolerant parsing and comment-preserving structural edits.
// The editor applies one splice at a time and revalidates the document after
// every edit, so an edit can never leave the file unparsable.

export class JsoncError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

type Token = {
  type: "punct" | "string" | "number" | "literal" | "comment" | "ws";
  start: number;
  end: number;
  raw: string;
};

type BaseNode = { start: number; end: number };
type ObjectNode = BaseNode & {
  kind: "object";
  props: Map<string, Node>;
  propOrder: string[];
  closeStart: number;
  trailingComma: boolean;
  empty: boolean;
};
type ArrayNode = BaseNode & {
  kind: "array";
  items: Node[];
  closeStart: number;
  trailingComma: boolean;
  empty: boolean;
};
type ScalarNode = BaseNode & { kind: "scalar"; raw: string };
type Node = ObjectNode | ArrayNode | ScalarNode;

export type JsoncPath = Array<string | number>;

export type JsoncEdit =
  | { kind: "append-unique"; path: JsoncPath; value: string }
  | { kind: "replace-array-value"; path: JsoncPath; from: string; to: string }
  | { kind: "set-if-absent"; path: JsoncPath; value: unknown }
  | { kind: "widen-scalar-map"; path: JsoncPath; entries: Record<string, string> };

export type JsoncEditResult = "created" | "present" | "appended" | "replaced" | "widened";

function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;
  const push = (type: Token["type"], start: number, end: number): void => {
    tokens.push({ type, start, end, raw: text.slice(start, end) });
  };
  while (index < text.length) {
    const character = text[index];
    if (character === " " || character === "\t" || character === "\r" || character === "\n") {
      const start = index;
      while (index < text.length && " \t\r\n".includes(text[index])) index += 1;
      push("ws", start, index);
      continue;
    }
    if (character === "/" && text[index + 1] === "/") {
      const start = index;
      while (index < text.length && text[index] !== "\n") index += 1;
      push("comment", start, index);
      continue;
    }
    if (character === "/" && text[index + 1] === "*") {
      const start = index;
      index += 2;
      while (index < text.length && !(text[index] === "*" && text[index + 1] === "/")) index += 1;
      if (index >= text.length)
        throw new JsoncError("invalid_jsonc", `Unterminated block comment at offset ${start}`);
      index += 2;
      push("comment", start, index);
      continue;
    }
    if (character === '"') {
      const start = index;
      index += 1;
      while (index < text.length && text[index] !== '"') {
        if (text[index] === "\\") index += 1;
        index += 1;
      }
      if (index >= text.length)
        throw new JsoncError("invalid_jsonc", `Unterminated string at offset ${start}`);
      index += 1;
      push("string", start, index);
      continue;
    }
    if (/[0-9-]/.test(character)) {
      const start = index;
      while (index < text.length && /[0-9+.eE-]/.test(text[index])) index += 1;
      push("number", start, index);
      continue;
    }
    if (/[a-z]/.test(character)) {
      const start = index;
      while (index < text.length && /[a-z]/.test(text[index])) index += 1;
      push("literal", start, index);
      continue;
    }
    if ("{}[]:,".includes(character)) {
      push("punct", index, index + 1);
      index += 1;
      continue;
    }
    throw new JsoncError("invalid_jsonc", `Unexpected character at offset ${index}`);
  }
  return tokens;
}

type Parser = { tokens: Token[]; cursor: number };

function significant(parser: Parser): Token | undefined {
  while (parser.cursor < parser.tokens.length) {
    const token = parser.tokens[parser.cursor];
    if (token.type === "ws" || token.type === "comment") {
      parser.cursor += 1;
      continue;
    }
    return token;
  }
  return undefined;
}

function expectPunct(parser: Parser, value: string): Token {
  const token = significant(parser);
  if (!token || token.type !== "punct" || token.raw !== value)
    throw new JsoncError(
      "invalid_jsonc",
      `Expected '${value}' at offset ${token ? token.start : (parser.tokens.at(-1)?.end ?? 0)}`,
    );
  parser.cursor += 1;
  return token;
}

function parseValue(parser: Parser): Node {
  const token = significant(parser);
  if (!token) throw new JsoncError("invalid_jsonc", "Unexpected end of document");
  if (token.type === "punct" && token.raw === "{") return parseObject(parser);
  if (token.type === "punct" && token.raw === "[") return parseArray(parser);
  if (token.type === "string" || token.type === "number" || token.type === "literal") {
    parser.cursor += 1;
    return { kind: "scalar", start: token.start, end: token.end, raw: token.raw };
  }
  throw new JsoncError("invalid_jsonc", `Unexpected token at offset ${token.start}`);
}

function parseObject(parser: Parser): ObjectNode {
  const open = expectPunct(parser, "{");
  const props = new Map<string, Node>();
  const propOrder: string[] = [];
  let trailingComma = false;
  let closeStart = open.end;
  let closed = false;
  for (;;) {
    const token = significant(parser);
    if (!token)
      throw new JsoncError("invalid_jsonc", `Unterminated object at offset ${open.start}`);
    if (token.type === "punct" && token.raw === "}") {
      closeStart = token.start;
      parser.cursor += 1;
      closed = true;
      break;
    }
    if (token.type !== "string")
      throw new JsoncError("invalid_jsonc", `Expected object key at offset ${token.start}`);
    const key = JSON.parse(token.raw) as string;
    parser.cursor += 1;
    expectPunct(parser, ":");
    const value = parseValue(parser);
    if (props.has(key))
      throw new JsoncError("invalid_jsonc", `Duplicate object key at offset ${token.start}`);
    props.set(key, value);
    propOrder.push(key);
    trailingComma = false;
    const next = significant(parser);
    if (next && next.type === "punct" && next.raw === ",") {
      parser.cursor += 1;
      trailingComma = true;
    }
  }
  if (!closed) throw new JsoncError("invalid_jsonc", `Unterminated object at offset ${open.start}`);
  return {
    kind: "object",
    start: open.start,
    end: closeStart + 1,
    props,
    propOrder,
    closeStart,
    trailingComma,
    empty: props.size === 0,
  };
}

function parseArray(parser: Parser): ArrayNode {
  const open = expectPunct(parser, "[");
  const items: Node[] = [];
  let trailingComma = false;
  let closeStart = open.end;
  let closed = false;
  for (;;) {
    const token = significant(parser);
    if (!token) throw new JsoncError("invalid_jsonc", `Unterminated array at offset ${open.start}`);
    if (token.type === "punct" && token.raw === "]") {
      closeStart = token.start;
      parser.cursor += 1;
      closed = true;
      break;
    }
    items.push(parseValue(parser));
    trailingComma = false;
    const next = significant(parser);
    if (next && next.type === "punct" && next.raw === ",") {
      parser.cursor += 1;
      trailingComma = true;
    }
  }
  if (!closed) throw new JsoncError("invalid_jsonc", `Unterminated array at offset ${open.start}`);
  return {
    kind: "array",
    start: open.start,
    end: closeStart + 1,
    items,
    closeStart,
    trailingComma,
    empty: items.length === 0,
  };
}

export function nodeToValue(node: Node): unknown {
  if (node.kind === "scalar") return JSON.parse(node.raw);
  if (node.kind === "array") return node.items.map(nodeToValue);
  const value: Record<string, unknown> = {};
  for (const key of node.propOrder) value[key] = nodeToValue(node.props.get(key)!);
  return value;
}

function parseDocument(text: string): Node {
  const parser: Parser = { tokens: tokenize(text), cursor: 0 };
  const node = parseValue(parser);
  const trailing = significant(parser);
  if (trailing)
    throw new JsoncError(
      "invalid_jsonc",
      `Unexpected trailing content at offset ${trailing.start}`,
    );
  return node;
}

export function parseJsonc(text: string): unknown {
  return nodeToValue(parseDocument(text));
}

function resolve(root: Node, path: JsoncPath): Node | undefined {
  let current: Node | undefined = root;
  for (const segment of path) {
    if (!current) return undefined;
    if (typeof segment === "string") {
      if (current.kind !== "object") return undefined;
      current = current.props.get(segment);
    } else {
      if (current.kind !== "array") return undefined;
      current = current.items[segment];
    }
  }
  return current;
}

function lineIndent(text: string, position: number): string {
  const lineStart = text.lastIndexOf("\n", Math.max(0, position - 1)) + 1;
  return /^[ \t]*/.exec(text.slice(lineStart, position))![0];
}

function serialize(value: unknown, indent: string): string {
  const rendered = JSON.stringify(value, null, 2);
  if (typeof value !== "object" || value === null) return rendered;
  return rendered
    .split("\n")
    .map((line, index) => (index === 0 ? line : `${indent}${line}`))
    .join("\n");
}

function insertObjectEntry(text: string, node: ObjectNode, key: string, value: unknown): string {
  const lastKey = node.propOrder.at(-1);
  const lastValue = lastKey ? node.props.get(lastKey)! : undefined;
  const at = lastValue ? lastValue.end : node.start + 1;
  const indent = lastValue
    ? lineIndent(text, lastValue.start)
    : `${lineIndent(text, node.closeStart)}  `;
  const entry = `${JSON.stringify(key)}: ${serialize(value, indent)}`;
  const insertion = lastValue
    ? `,\n${indent}${entry}`
    : `\n${indent}${entry}\n${lineIndent(text, node.closeStart)}`;
  return text.slice(0, at) + insertion + text.slice(at);
}

function requireObjectPath(
  text: string,
  root: Node,
  path: JsoncPath,
): { text: string; node: ObjectNode } {
  let currentText = text;
  for (let depth = 0; depth < path.length; depth += 1) {
    const segment = path[depth];
    if (typeof segment !== "string")
      throw new JsoncError("unsupported_edit", "Object path segments must be strings");
    const document = parseDocument(currentText);
    if (resolve(document, path.slice(0, depth + 1))) continue;
    const parent = resolve(document, path.slice(0, depth));
    if (!parent || parent.kind !== "object")
      throw new JsoncError("conflict", `Path parent is not an object: ${segment}`);
    currentText = insertObjectEntry(currentText, parent, segment, {});
  }
  const node = resolve(parseDocument(currentText), path);
  if (!node || node.kind !== "object")
    throw new JsoncError("conflict", "Path target is missing or not an object");
  return { text: currentText, node };
}

function applyEdit(
  text: string,
  root: Node,
  edit: JsoncEdit,
): { text: string; result: JsoncEditResult } {
  if (edit.kind === "append-unique") {
    const target = resolve(root, edit.path);
    if (!target || target.kind !== "array")
      throw new JsoncError("conflict", "append-unique target is missing or not an array");
    if (target.items.map(nodeToValue).includes(edit.value)) return { text, result: "present" };
    const insertion = target.empty ? JSON.stringify(edit.value) : `, ${JSON.stringify(edit.value)}`;
    const at = target.empty ? target.start + 1 : target.items.at(-1)!.end;
    return { text: text.slice(0, at) + insertion + text.slice(at), result: "appended" };
  }
  if (edit.kind === "replace-array-value") {
    const target = resolve(root, edit.path);
    if (!target || target.kind !== "array")
      throw new JsoncError("conflict", "replace-array-value target is missing or not an array");
    const index = target.items.map(nodeToValue).indexOf(edit.from);
    if (index === -1) return { text, result: "present" };
    const node = target.items[index];
    return {
      text: text.slice(0, node.start) + JSON.stringify(edit.to) + text.slice(node.end),
      result: "replaced",
    };
  }
  if (edit.kind === "set-if-absent") {
    const key = edit.path.at(-1);
    if (typeof key !== "string")
      throw new JsoncError("unsupported_edit", "set-if-absent requires a string object key");
    const parentPath = edit.path.slice(0, -1);
    const parent = resolve(root, parentPath);
    if (parent && parent.kind === "object" && parent.props.has(key))
      return { text, result: "present" };
    const ensured = requireObjectPath(text, root, parentPath);
    if (ensured.node.props.has(key)) return { text, result: "present" };
    return {
      text: insertObjectEntry(ensured.text, ensured.node, key, edit.value),
      result: "created",
    };
  }
  const target = resolve(root, edit.path);
  if (!target) {
    const ensured = requireObjectPath(text, root, edit.path);
    let currentText = ensured.text;
    let changed = false;
    for (const [key, value] of Object.entries(edit.entries)) {
      const node = resolve(parseDocument(currentText), edit.path);
      if (!node || node.kind !== "object")
        throw new JsoncError("conflict", "widen-scalar-map target stopped being an object");
      if (node.props.has(key)) continue;
      currentText = insertObjectEntry(currentText, node, key, value);
      changed = true;
    }
    return { text: currentText, result: changed ? "created" : "present" };
  }
  if (target.kind === "object") {
    let currentText = text;
    let changed = false;
    for (const [key, value] of Object.entries(edit.entries)) {
      const node = resolve(parseDocument(currentText), edit.path);
      if (!node || node.kind !== "object")
        throw new JsoncError("conflict", "widen-scalar-map target stopped being an object");
      if (node.props.has(key)) continue;
      currentText = insertObjectEntry(currentText, node, key, value);
      changed = true;
    }
    return { text: currentText, result: changed ? "created" : "present" };
  }
  if (target.kind !== "scalar" || !/^(?:"(?:[^"\\]|\\.)*"|true|false|null)$/.test(target.raw))
    throw new JsoncError("conflict", "widen-scalar-map target is neither a map nor a scalar");
  const parentIndent = lineIndent(text, target.start);
  const childIndent = `${parentIndent}  `;
  const lines = [`"*": ${target.raw}`];
  for (const [key, value] of Object.entries(edit.entries)) {
    if (key === "*") continue;
    lines.push(`${JSON.stringify(key)}: ${JSON.stringify(value)}`);
  }
  const replacement = `{\n${childIndent}${lines.join(`,\n${childIndent}`)}\n${parentIndent}}`;
  return {
    text: text.slice(0, target.start) + replacement + text.slice(target.end),
    result: "widened",
  };
}

function at(value: unknown, path: JsoncPath): unknown {
  return path.reduce<unknown>(
    (current, segment) =>
      current && typeof current === "object"
        ? (current as Record<string | number, unknown>)[segment]
        : undefined,
    value,
  );
}

function verifyEdit(before: unknown, after: unknown, edit: JsoncEdit): void {
  if (edit.kind === "append-unique") {
    const target = at(after, edit.path);
    if (!Array.isArray(target) || !target.includes(edit.value))
      throw new JsoncError("merge_validation_failed", "append-unique postcondition failed");
    return;
  }
  if (edit.kind === "replace-array-value") {
    const beforeTarget = at(before, edit.path);
    const afterTarget = at(after, edit.path);
    if (Array.isArray(beforeTarget) && beforeTarget.includes(edit.from)) {
      if (
        !Array.isArray(afterTarget) ||
        !afterTarget.includes(edit.to) ||
        afterTarget.includes(edit.from)
      )
        throw new JsoncError("merge_validation_failed", "replace-array-value postcondition failed");
    }
    return;
  }
  if (edit.kind === "set-if-absent") {
    const key = edit.path.at(-1) as string;
    const parentPath = edit.path.slice(0, -1);
    const parentAfter = at(after, parentPath);
    if (
      !parentAfter ||
      typeof parentAfter !== "object" ||
      Array.isArray(parentAfter) ||
      !(key in (parentAfter as object))
    )
      throw new JsoncError("merge_validation_failed", "set-if-absent postcondition failed");
    const parentBefore = at(before, parentPath);
    if (
      parentBefore &&
      typeof parentBefore === "object" &&
      !Array.isArray(parentBefore) &&
      key in (parentBefore as object) &&
      JSON.stringify((parentBefore as Record<string, unknown>)[key]) !==
        JSON.stringify((parentAfter as Record<string, unknown>)[key])
    )
      throw new JsoncError("merge_validation_failed", "set-if-absent modified an existing entry");
    return;
  }
  const target = at(after, edit.path);
  if (!target || typeof target !== "object" || Array.isArray(target))
    throw new JsoncError("merge_validation_failed", "widen-scalar-map postcondition failed");
  for (const [key, value] of Object.entries(edit.entries)) {
    if ((target as Record<string, unknown>)[key] !== value)
      throw new JsoncError("merge_validation_failed", "widen-scalar-map entry missing");
  }
  const beforeTarget = at(before, edit.path);
  if (
    beforeTarget !== undefined &&
    (typeof beforeTarget !== "object" || beforeTarget === null || Array.isArray(beforeTarget)) &&
    (target as Record<string, unknown>)["*"] !== beforeTarget
  )
    throw new JsoncError("merge_validation_failed", "widened map lost the original scalar value");
}

export function applyJsoncEdits(
  text: string,
  edits: readonly JsoncEdit[],
): { text: string; results: JsoncEditResult[]; changed: boolean } {
  const before = parseJsonc(text);
  let current = text;
  const results: JsoncEditResult[] = [];
  for (const edit of edits) {
    const applied = applyEdit(current, parseDocument(current), edit);
    verifyEdit(before, parseJsonc(applied.text), edit);
    results.push(applied.result);
    current = applied.text;
  }
  return { text: current, results, changed: current !== text };
}
