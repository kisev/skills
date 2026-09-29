export type Strings = {
  title: string;
  target: string;
  verdict: string;
  items: string;
  pending: string;
  applied: string;
  skipped: string;
  error: string;
  keysOverview: string;
  keysDetail: string;
  keysWorktree: string;
  replyDraft: string;
  remark: string;
  suggestion: string;
  patch: string;
  labels: string;
  labelsAdd: string;
  labelsRemove: string;
  issueTitle: string;
  send: string;
  sendResolve: string;
  skip: string;
  edit: string;
  applyLocal: string;
  back: string;
  quit: string;
  busy: string;
  done: string;
  resultSend: string;
  worktreeExplain: string;
  worktreeRepository: string;
  worktreeBranch: string;
  worktreeHead: string;
  worktreePath: string;
  worktreeFiles: string;
  worktreeApply: string;
  worktreeDiff: string;
  worktreeCommit: string;
  worktreePush: string;
  worktreeCommitMessage: string;
  worktreePushPreview: string;
  noFix: string;
  nothing: string;
  confirm: string;
  cancelled: string;
  edited: string;
  unchanged: string;
};

const en: Strings = {
  title: "reviewmatic",
  target: "target",
  verdict: "verdict",
  items: "plan items",
  pending: "pending",
  applied: "sent",
  skipped: "skipped",
  error: "error",
  keysOverview: "↑/↓ select · enter open · q quit",
  keysDetail: "e edit · s send · S send+resolve · a apply locally · x skip · esc back",
  keysWorktree: "enter apply · v diff · c commit · p push · esc back",
  replyDraft: "reply draft",
  remark: "remark",
  suggestion: "suggestion",
  patch: "patch",
  labels: "labels",
  labelsAdd: "add",
  labelsRemove: "remove",
  issueTitle: "issue",
  send: "send",
  sendResolve: "send and resolve",
  skip: "skip",
  edit: "edit",
  applyLocal: "apply locally",
  back: "back",
  quit: "quit",
  busy: "working…",
  done: "done",
  resultSend: "publication result",
  worktreeExplain: "local application preview",
  worktreeRepository: "repository",
  worktreeBranch: "branch",
  worktreeHead: "head",
  worktreePath: "worktree",
  worktreeFiles: "files",
  worktreeApply: "apply patch in a dedicated worktree",
  worktreeDiff: "diff",
  worktreeCommit: "commit",
  worktreePush: "push",
  worktreeCommitMessage: "commit message",
  worktreePushPreview: "push command",
  noFix: "this item has no local fix",
  nothing: "nothing to show",
  confirm: "y confirm · esc cancel",
  cancelled: "cancelled",
  edited: "body edited",
  unchanged: "unchanged",
};

const ru: Strings = {
  title: "reviewmatic",
  target: "цель",
  verdict: "вердикт",
  items: "пункты плана",
  pending: "ожидает",
  applied: "отправлено",
  skipped: "пропущено",
  error: "ошибка",
  keysOverview: "↑/↓ выбор · enter открыть · q выход",
  keysDetail:
    "e правка · s отправить · S отправить и закрыть · a применить локально · x пропустить · esc назад",
  keysWorktree: "enter применить · v diff · c коммит · p пуш · esc назад",
  replyDraft: "черновик ответа",
  remark: "замечание",
  suggestion: "саджест",
  patch: "патч",
  labels: "лейблы",
  labelsAdd: "добавить",
  labelsRemove: "убрать",
  issueTitle: "issue",
  send: "отправить",
  sendResolve: "отправить и закрыть",
  skip: "пропустить",
  edit: "правка",
  applyLocal: "применить локально",
  back: "назад",
  quit: "выход",
  busy: "выполняется…",
  done: "готово",
  resultSend: "результат публикации",
  worktreeExplain: "предпросмотр локального применения",
  worktreeRepository: "репозиторий",
  worktreeBranch: "ветка",
  worktreeHead: "head",
  worktreePath: "ворктри",
  worktreeFiles: "файлы",
  worktreeApply: "применить патч в отдельном ворктри",
  worktreeDiff: "diff",
  worktreeCommit: "коммит",
  worktreePush: "пуш",
  worktreeCommitMessage: "сообщение коммита",
  worktreePushPreview: "команда пуша",
  noFix: "у пункта нет локального фикса",
  nothing: "нечего показать",
  confirm: "y подтвердить · esc отмена",
  cancelled: "отменено",
  edited: "тело отредактировано",
  unchanged: "без изменений",
};

export function stringsFor(locale: string | null | undefined): Strings {
  return locale === "ru" ? ru : en;
}
