import React, { useCallback, useEffect, useState } from "react";
import { render, useInput, useApp, Box, Text } from "ink";
import {
  type PlanBundle,
  type PlanItem,
  planItems,
  sendItem,
  editInEditor,
  planRepository,
  itemText,
  visualLines,
  displayText,
  terminalLink,
  openLink,
} from "./support.js";
import { stringsFor, type Strings } from "./strings.js";
import {
  prepareApplication,
  commitApplication,
  pushApplication,
  suggestionToPatch,
  type ApplicationResult,
} from "../worktree.js";

type Status = "pending" | "applied" | "replied" | "skipped" | "error";

type WorktreeState = {
  item: PlanItem;
  application: ApplicationResult;
  commitMessage: string;
  commitSha: string | null;
  pushed: boolean;
};

type EditTarget = { kind: "body"; key: string; body: string } | { kind: "commit"; message: string };

function statusMark(status: Status | undefined, strings: Strings): string {
  switch (status) {
    case "applied":
      return `[+] ${strings.applied}`;
    case "replied":
      return `[+] ${strings.replied}`;
    case "skipped":
      return `[.] ${strings.skipped}`;
    case "error":
      return `[!] ${strings.error}`;
    default:
      return `[ ] ${strings.pending}`;
  }
}

function kindLabel(item: PlanItem, strings: Strings): string {
  switch (item.kind) {
    case "thread":
      return strings.remark;
    case "line":
      return strings.suggestion;
    case "issue":
      return strings.issueTitle;
    case "labels":
      return strings.labels;
    default:
      return "note";
  }
}

const Viewport: React.FC<{ text: string; offset: number; height: number; width: number }> = ({
  text,
  offset,
  height,
  width,
}) => {
  const lines = visualLines(text, width);
  const visible = lines.slice(offset, offset + height);
  return (
    <Box flexDirection="column">
      {visible.map((line, position) => (
        <Box key={position}>
          <Text>{line.length === 0 ? " " : line}</Text>
        </Box>
      ))}
    </Box>
  );
};

const DiffView: React.FC<{ diff: string; height: number }> = ({ diff, height }) => {
  const lines = diff.replace(/\n$/, "").split("\n").slice(-height);
  return (
    <Box flexDirection="column">
      {lines.map((line, position) => {
        const color = line.startsWith("+")
          ? "green"
          : line.startsWith("-")
            ? "red"
            : line.startsWith("@@")
              ? "cyan"
              : undefined;
        return (
          <Box key={position}>
            <Text color={color}>{line.length === 0 ? " " : line.slice(0, 200)}</Text>
          </Box>
        );
      })}
    </Box>
  );
};

export function ReviewApp(props: {
  initial: TuiState;
  strings: Strings;
  persist: (state: TuiState) => void;
  request: (request: { kind: "quit" } | { kind: "edit"; target: EditTarget }) => void;
}): React.ReactElement {
  const { strings, request } = props;
  const { exit } = useApp();
  const [bundle, setBundle] = useState(props.initial.bundle);
  const [items] = useState(props.initial.items);
  const [view, setView] = useState<"overview" | "detail">(props.initial.view);
  const [index, setIndex] = useState(props.initial.index);
  const [offset, setOffset] = useState(props.initial.offset);
  const [statuses, setStatuses] = useState<Record<string, Status>>(props.initial.statuses);
  const [messages, setMessages] = useState<string[]>(props.initial.messages);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<null | { label: string; operation: () => void }>(
    null,
  );
  const [worktree, setWorktree] = useState<WorktreeState | null>(props.initial.worktree);
  const [editedBodies, setEditedBodies] = useState<Record<string, string>>(
    props.initial.editedBodies,
  );
  const [terminalHeight, setTerminalHeight] = useState(process.stdout.rows ?? 24);
  const [terminalWidth, setTerminalWidth] = useState(process.stdout.columns ?? 80);
  useEffect(() => {
    const resize = (): void => {
      setTerminalHeight(process.stdout.rows ?? 24);
      setTerminalWidth(process.stdout.columns ?? 80);
    };
    process.stdout.on("resize", resize);
    return () => {
      process.stdout.off("resize", resize);
    };
  }, []);
  const detailHeight = Math.max(1, terminalHeight - 14);
  const detailWidth = Math.max(2, terminalWidth - 6);
  const item = items[index] ?? null;
  const body = item !== null ? (editedBodies[item.key] ?? item.body ?? strings.nothing) : "";
  const fix =
    item !== null && ["patch", "suggestion"].includes(String(item.detail.fix_mode))
      ? item.detail
      : null;
  const detailText = item !== null ? itemText(item, strings, editedBodies[item.key]) : "";
  const lines = visualLines(detailText, detailWidth).length;
  const clampedOffset = Math.min(offset, Math.max(0, lines - detailHeight));
  useEffect(() => {
    props.persist({
      bundle,
      items,
      view,
      index,
      offset,
      statuses,
      messages,
      busy,
      worktree,
      editedBodies,
    });
  }, [bundle, items, view, index, offset, statuses, messages, busy, worktree, editedBodies, props]);

  const perform = useCallback(
    async (operation: () => Promise<void>): Promise<void> => {
      setBusy(true);
      setMessages([]);
      try {
        await operation();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (item !== null) setStatuses((current) => ({ ...current, [item.key]: "error" }));
        setMessages([message]);
      }
      setBusy(false);
    },
    [item],
  );

  const doSend = useCallback(
    (resolveToo: boolean): void => {
      if (item === null || busy) return;
      const target = item;
      void perform(async () => {
        const actions = resolveToo
          ? target.actions
          : target.actions.filter(
              (action) => action.operation !== "resolve" && action.operation !== "reopen",
            );
        const { bundle: nextBundle, results } = await sendItem(
          bundle,
          { ...target, actions },
          editedBodies[target.key] ?? null,
        );
        const failed = results.some(
          (result) => (result as { status?: string }).status === "blocked",
        );
        setBundle(nextBundle);
        setStatuses((current) => ({
          ...current,
          [target.key]: failed
            ? "error"
            : actions.length < target.actions.length
              ? "replied"
              : "applied",
        }));
        setMessages(results.map((result) => JSON.stringify(result)));
      });
    },
    [bundle, busy, editedBodies, item, perform],
  );

  const doApplyLocal = useCallback((): void => {
    if (item === null || busy) return;
    const target = item;
    const fixRecord = (fix ?? {}) as { fix_mode?: string; patch?: string; suggestion?: string };
    void perform(async () => {
      const repository = await planRepository(bundle);
      if (
        repository.repoRoot === null ||
        repository.branch === null ||
        repository.headSha === null
      ) {
        throw new Error(strings.noFix);
      }
      const patch =
        fixRecord.fix_mode === "patch" && typeof fixRecord.patch === "string"
          ? fixRecord.patch
          : suggestionToPatch({
              repoRoot: repository.repoRoot,
              headSha: repository.headSha,
              newPath: target.path ?? "",
              oldPath: target.path ?? "",
              newLine: target.line,
              oldLine: null,
              suggestion:
                typeof fixRecord.suggestion === "string" && fixRecord.suggestion !== ""
                  ? fixRecord.suggestion
                  : body,
            });
      const mrUrl = String((bundle.plan.target as { url?: string }).url ?? "");
      const application = await prepareApplication({
        repoRoot: repository.repoRoot,
        branch: repository.branch,
        headSha: repository.headSha,
        patch,
        mrUrl,
      });
      setWorktree({
        item: target,
        application,
        commitMessage: `fix: ${target.title}`.split("\n")[0].slice(0, 72),
        commitSha: null,
        pushed: false,
      });
    });
  }, [body, bundle, busy, fix, item, perform, strings.noFix]);

  const doCommit = useCallback((): void => {
    if (worktree === null || busy) return;
    const target = worktree;
    void perform(async () => {
      const { commit_sha: commitSha } = commitApplication(
        target.application.explanation.worktree_path,
        target.commitMessage,
      );
      setWorktree({ ...target, commitSha });
      setMessages([`${strings.worktreeCommit}: ${commitSha.slice(0, 12)}`]);
    });
  }, [busy, perform, strings.worktreeCommit, worktree]);

  const doPush = useCallback((): void => {
    if (worktree === null || busy) return;
    const target = worktree;
    void perform(async () => {
      pushApplication({
        worktreePath: target.application.explanation.worktree_path,
        branch: target.application.explanation.branch,
      });
      setWorktree({ ...target, pushed: true });
      setMessages([`${strings.worktreePush}: ${target.application.explanation.branch}`]);
    });
  }, [busy, perform, strings.worktreePush, worktree]);

  useInput((input, key) => {
    if (busy) return;
    if (confirmation !== null) {
      if (key.escape || input === "n") setConfirmation(null);
      else if (input === "y") {
        const operation = confirmation.operation;
        setConfirmation(null);
        operation();
      }
      return;
    }
    if (key.escape) {
      if (worktree !== null) {
        setWorktree(null);
        return;
      }
      if (view === "detail") {
        setView("overview");
        setOffset(0);
        return;
      }
      exit();
      request({ kind: "quit" });
      return;
    }
    if (worktree !== null) {
      if (input === "c" && worktree.commitSha === null) {
        request({ kind: "edit", target: { kind: "commit", message: worktree.commitMessage } });
        return;
      }
      if (input === "C") {
        if (worktree.commitSha === null)
          setConfirmation({
            label: `${strings.worktreeCommit}: ${worktree.commitMessage}`,
            operation: doCommit,
          });
        return;
      }
      if (input === "p" && worktree.commitSha !== null && !worktree.pushed) {
        setConfirmation({
          label: `${strings.worktreePush}: ${worktree.application.explanation.branch}`,
          operation: doPush,
        });
        return;
      }
      return;
    }
    if (input === "q" && view === "overview") {
      exit();
      request({ kind: "quit" });
      return;
    }
    if (view === "overview") {
      if (key.pageUp || key.pageDown) {
        setIndex((current) =>
          Math.max(
            0,
            Math.min(
              items.length - 1,
              current +
                (key.pageUp ? -Math.max(1, terminalHeight - 7) : Math.max(1, terminalHeight - 7)),
            ),
          ),
        );
        return;
      }
      if (key.upArrow || input === "k") {
        setIndex((current) => (current > 0 ? current - 1 : items.length - 1));
        return;
      }
      if (key.downArrow || input === "j") {
        setIndex((current) => (current < items.length - 1 ? current + 1 : 0));
        return;
      }
      if (key.return && items.length > 0) {
        setView("detail");
        setOffset(0);
      }
      return;
    }
    if (item === null) return;
    if (input === "o" && item.url !== null) {
      void perform(() => openLink(item.url!));
      return;
    }
    if (key.leftArrow || key.rightArrow || input === "[" || input === "]") {
      setIndex(
        (current) =>
          (current + (key.leftArrow || input === "[" ? -1 : 1) + items.length) % items.length,
      );
      setOffset(0);
      return;
    }
    if (key.pageUp || key.pageDown) {
      setOffset(
        Math.max(
          0,
          Math.min(
            lines - detailHeight,
            clampedOffset + (key.pageUp ? -detailHeight : detailHeight),
          ),
        ),
      );
      return;
    }
    if (key.upArrow || input === "k") {
      setOffset(Math.max(0, clampedOffset - 1));
      return;
    }
    if (key.downArrow || input === "j") {
      setOffset(Math.min(Math.max(0, lines - detailHeight), clampedOffset + 1));
      return;
    }
    if (
      input === "s" &&
      item.actions.some((action) => action.operation !== "resolve" && action.operation !== "reopen")
    ) {
      setConfirmation({ label: strings.send, operation: () => doSend(false) });
      return;
    }
    if (
      input === "S" &&
      item.actions.some((action) => action.operation === "resolve" || action.operation === "reopen")
    ) {
      setConfirmation({
        label: `${strings.send}: ${String(item.detail.outcome)}`,
        operation: () => doSend(true),
      });
      return;
    }
    if (input === "x") {
      setStatuses((current) => ({ ...current, [item.key]: "skipped" }));
      setView("overview");
      return;
    }
    if (
      input === "e" &&
      item.body !== null &&
      item.actions.length > 0 &&
      !["applied", "replied"].includes(statuses[item.key])
    ) {
      request({ kind: "edit", target: { kind: "body", key: item.key, body } });
      return;
    }
    if (input === "a" && fix !== null) {
      setConfirmation({ label: strings.worktreeApply, operation: doApplyLocal });
    }
  });

  const plan = bundle.plan as { verdict?: string; target?: { url?: string } };
  const applied = Object.values(statuses).filter((value) => value === "applied").length;
  const listHeight = Math.max(1, terminalHeight - 7);
  const listStart = Math.max(
    0,
    Math.min(index - Math.floor(listHeight / 2), items.length - listHeight),
  );
  return (
    <Box flexDirection="column" borderStyle="round" paddingX={1}>
      <Box>
        <Text bold color="cyan" wrap="truncate-end">
          {strings.title} · {strings.verdict}: {String(plan.verdict ?? "?")} · {applied}/
          {items.filter((entry) => entry.actions.length > 0).length} {strings.items}
        </Text>
      </Box>
      <Box>
        <Text dimColor wrap="truncate-end">
          {strings.target}: {terminalLink(plan.target?.url ?? null)}
        </Text>
      </Box>
      {view === "overview" ? (
        <Box flexDirection="column">
          {items.slice(listStart, listStart + listHeight).map((entry, localPosition) => {
            const position = listStart + localPosition;
            return (
              <Box key={entry.key}>
                <Text color={position === index ? "cyan" : undefined} wrap="truncate-end">
                  {position === index ? "❯ " : "  "}
                  {entry.actions.length === 0 &&
                  !["patch", "suggestion"].includes(String(entry.detail.fix_mode))
                    ? `[-] ${strings.readOnlyShort} `
                    : `${statusMark(statuses[entry.key], strings)} `}
                  ({kindLabel(entry, strings)}){" "}
                  {entry.path !== null
                    ? `${entry.path}${entry.line !== null ? `:${entry.line}` : ""} `
                    : ""}
                  {displayText(entry.title)}
                </Text>
              </Box>
            );
          })}
          <Text dimColor>
            {items.length === 0 ? strings.nothing : `${index + 1}/${items.length}`}
          </Text>
          <Text dimColor>{strings.keysOverview}</Text>
        </Box>
      ) : item === null ? (
        <Text>{strings.nothing}</Text>
      ) : (
        <Box flexDirection="column">
          <Box>
            <Text bold color="yellow" wrap="truncate-end">
              {kindLabel(item, strings)}{" "}
              {item.path !== null
                ? `${item.path}${item.line !== null ? `:${item.line}` : ""}`
                : displayText(item.title)}
            </Text>
          </Box>
          {item.url !== null ? (
            <Text color="cyan" wrap="truncate-end">
              {terminalLink(
                item.url,
                undefined,
                `GitLab ${strings.discussion} ${item.url.includes("#note_") ? item.url.split("#note_")[1] : ""}`,
              )}
            </Text>
          ) : null}
          {worktree !== null ? (
            <Box flexDirection="column">
              <Text bold>{strings.worktreeExplain}</Text>
              <Text>
                {strings.worktreeBranch}: {worktree.application.explanation.branch} @{" "}
                {worktree.application.explanation.head_sha.slice(0, 12)}
              </Text>
              <Text dimColor>
                {strings.worktreePath}: {worktree.application.explanation.worktree_path}
              </Text>
              <Text>
                {strings.worktreeFiles}: {worktree.application.explanation.files.join(", ") || "-"}
              </Text>
              {worktree.commitSha !== null ? (
                <Text color="green">
                  {strings.worktreeCommit}: {worktree.commitSha.slice(0, 12)}
                  {worktree.pushed ? ` · ${strings.worktreePush} ✓` : ""}
                </Text>
              ) : null}
              <DiffView diff={worktree.application.diff} height={Math.min(12, detailHeight)} />
              <Text dimColor>{strings.keysWorktree}</Text>
            </Box>
          ) : (
            <Box flexDirection="column">
              <Viewport
                text={detailText}
                offset={clampedOffset}
                height={detailHeight}
                width={detailWidth}
              />
              <Text dimColor>
                {strings.scroll}: {clampedOffset + 1}-
                {Math.min(lines, clampedOffset + detailHeight)}/{lines}
              </Text>
              <Text dimColor wrap="truncate-end">
                {item.actions.length === 0 && fix === null ? strings.readOnly : strings.keysDetail}
              </Text>
            </Box>
          )}
        </Box>
      )}
      {busy ? <Text color="yellow">{strings.busy}</Text> : null}
      {confirmation !== null ? (
        <Text bold color="yellow">
          {displayText(confirmation.label)} · {strings.confirm}
        </Text>
      ) : null}
      {messages.slice(-2).map((message, position) => (
        <Text key={position} color="green" wrap="truncate-end">
          {displayText(message)}
        </Text>
      ))}
    </Box>
  );
}

export type TuiState = {
  bundle: PlanBundle;
  items: PlanItem[];
  view: "overview" | "detail";
  index: number;
  offset: number;
  statuses: Record<string, Status>;
  messages: string[];
  busy: boolean;
  worktree: WorktreeState | null;
  editedBodies: Record<string, string>;
};

export async function runTui(initialBundle: PlanBundle): Promise<number> {
  const strings = stringsFor((initialBundle.plan.locale as string) ?? "en");
  let state: TuiState = {
    bundle: initialBundle,
    items: planItems(initialBundle),
    view: "overview",
    index: 0,
    offset: 0,
    statuses: {},
    messages: [],
    busy: false,
    worktree: null,
    editedBodies: {},
  };
  for (;;) {
    const outcome = await new Promise<{ kind: "quit" } | { kind: "edit"; target: EditTarget }>(
      (resolve) => {
        const instance = render(
          <ReviewApp
            initial={state}
            strings={strings}
            persist={(snapshot) => {
              state = snapshot;
            }}
            request={(outcome) => {
              resolve(outcome);
              instance.unmount();
            }}
          />,
          { exitOnCtrlC: true, interactive: true },
        );
        void instance.waitUntilExit().then(() => resolve({ kind: "quit" }));
      },
    );
    if (outcome.kind === "quit") return 0;
    if (outcome.target.kind === "body") {
      const edited = editInEditor(outcome.target.body);
      if (edited !== null) {
        state = {
          ...state,
          editedBodies: { ...state.editedBodies, [outcome.target.key]: edited },
          messages: [strings.edited],
        };
      } else {
        state = { ...state, messages: [strings.unchanged] };
      }
    } else {
      const edited = editInEditor(`${outcome.target.message}\n`);
      if (edited !== null && edited.trim() !== "" && state.worktree !== null) {
        state = {
          ...state,
          worktree: { ...state.worktree, commitMessage: edited.trim() },
          messages: [strings.edited],
        };
      }
    }
  }
}
