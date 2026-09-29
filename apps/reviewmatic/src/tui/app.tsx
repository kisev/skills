import React, { useCallback, useEffect, useState } from "react";
import { render, useInput, useApp, Box, Text } from "ink";
import {
  type PlanBundle,
  type PlanItem,
  planItems,
  sendItem,
  editInEditor,
  planRepository,
} from "./support.js";
import { stringsFor, type Strings } from "./strings.js";
import {
  prepareApplication,
  commitApplication,
  pushApplication,
  suggestionToPatch,
  type ApplicationResult,
} from "../worktree.js";

type Status = "pending" | "applied" | "skipped" | "error";

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

const Viewport: React.FC<{ text: string; offset: number; height: number }> = ({
  text,
  offset,
  height,
}) => {
  const lines = text.replace(/\n$/, "").split("\n");
  const visible = lines.slice(offset, offset + height);
  return (
    <Box flexDirection="column">
      {visible.map((line, position) => (
        <Box key={position}>
          <Text>{line.length === 0 ? " " : line.slice(0, 200)}</Text>
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

function App(props: {
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
  const [worktree, setWorktree] = useState<WorktreeState | null>(props.initial.worktree);
  const [editedBodies, setEditedBodies] = useState<Record<string, string>>(
    props.initial.editedBodies,
  );
  const [terminalHeight, setTerminalHeight] = useState(process.stdout.rows ?? 24);
  useEffect(() => {
    const resize = (): void => setTerminalHeight(process.stdout.rows ?? 24);
    process.stdout.on("resize", resize);
    return () => {
      process.stdout.off("resize", resize);
    };
  }, []);
  const detailHeight = Math.max(4, terminalHeight - 14);
  const item = items[index] ?? null;
  const body = item !== null ? (editedBodies[item.key] ?? item.body ?? strings.nothing) : "";
  const fix =
    item !== null ? ((item.detail as { fix?: Record<string, unknown> }).fix ?? null) : null;
  const lines = body.replace(/\n$/, "").split("\n").length;
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
        setStatuses((current) => ({ ...current, [target.key]: failed ? "error" : "applied" }));
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
        doCommit();
        return;
      }
      if (input === "p" && worktree.commitSha !== null && !worktree.pushed) {
        doPush();
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
    if (key.upArrow || input === "k") {
      setOffset((current) => Math.max(0, current - 1));
      return;
    }
    if (key.downArrow || input === "j") {
      setOffset((current) => Math.min(Math.max(0, lines - detailHeight), current + 1));
      return;
    }
    if (input === "s" || key.return) {
      doSend(false);
      return;
    }
    if (input === "S") {
      doSend(true);
      return;
    }
    if (input === "x") {
      setStatuses((current) => ({ ...current, [item.key]: "skipped" }));
      setView("overview");
      return;
    }
    if (input === "e" && item.body !== null) {
      request({ kind: "edit", target: { kind: "body", key: item.key, body } });
      return;
    }
    if (input === "a" && fix !== null) {
      doApplyLocal();
    }
  });

  const plan = bundle.plan as { verdict?: string; target?: { url?: string } };
  const applied = Object.values(statuses).filter((value) => value === "applied").length;
  return (
    <Box flexDirection="column" borderStyle="round" paddingX={1}>
      <Box>
        <Text bold color="cyan">
          {strings.title}
        </Text>
        <Text> · {strings.verdict}: </Text>
        <Text bold>{String(plan.verdict ?? "?")}</Text>
        <Text dimColor>
          {" "}
          · {applied}/{items.length} {strings.items}
        </Text>
      </Box>
      <Box>
        <Text dimColor>
          {strings.target}: {String(plan.target?.url ?? "")}
        </Text>
      </Box>
      {view === "overview" ? (
        <Box flexDirection="column">
          {items.map((entry, position) => (
            <Box key={entry.key}>
              <Text color={position === index ? "cyan" : undefined}>
                {position === index ? "❯ " : "  "}
                {statusMark(statuses[entry.key], strings)}{" "}
              </Text>
              <Text dimColor>({kindLabel(entry, strings)}) </Text>
              <Text>
                {entry.path !== null
                  ? `${entry.path}${entry.line !== null ? `:${entry.line}` : ""} `
                  : ""}
                {entry.title.slice(0, 80)}
              </Text>
            </Box>
          ))}
          <Text dimColor>{strings.keysOverview}</Text>
        </Box>
      ) : item === null ? (
        <Text>{strings.nothing}</Text>
      ) : (
        <Box flexDirection="column">
          <Box>
            <Text bold color="yellow">
              {kindLabel(item, strings)}
            </Text>
            <Text>
              {" "}
              {item.path !== null
                ? `${item.path}${item.line !== null ? `:${item.line}` : ""}`
                : item.title}
            </Text>
          </Box>
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
              <Text bold dimColor>
                {item.kind === "labels" ? strings.labels : strings.replyDraft}:
              </Text>
              <Viewport
                text={
                  item.kind === "labels"
                    ? [
                        `${strings.labelsAdd}: ${((item.detail as { add?: string[] }).add ?? []).join(", ") || "-"}`,
                        `${strings.labelsRemove}: ${((item.detail as { remove?: string[] }).remove ?? []).join(", ") || "-"}`,
                      ].join("\n")
                    : body
                }
                offset={offset}
                height={detailHeight}
              />
              <Text dimColor>{strings.keysDetail}</Text>
            </Box>
          )}
        </Box>
      )}
      {busy ? <Text color="yellow">{strings.busy}</Text> : null}
      {messages.map((message, position) => (
        <Text key={position} color="green" wrap="truncate-end">
          {message.slice(0, 200)}
        </Text>
      ))}
    </Box>
  );
}

type TuiState = {
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
          <App
            initial={state}
            strings={strings}
            persist={(snapshot) => {
              state = snapshot;
            }}
            request={resolve}
          />,
          { exitOnCtrlC: true },
        );
        void instance;
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
