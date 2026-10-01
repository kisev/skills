export type Strings = {
  title: string;
  target: string;
  verdict: string;
  items: string;
  pending: string;
  applied: string;
  replied: string;
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
  discussion: string;
  assessment: string;
  systemNote: string;
  noPublication: string;
  readOnly: string;
  readOnlyShort: string;
  scroll: string;
};

const en: Strings = {
  title: "reviewmatic",
  target: "target",
  verdict: "verdict",
  items: "publication items",
  pending: "pending",
  applied: "sent",
  replied: "reply sent; state unchanged",
  skipped: "skipped",
  error: "error",
  keysOverview: "↑/↓ select · enter open · q quit",
  keysDetail:
    "↑/↓ scroll · ←/→ item · o browser · e edit · s send only · S send+state · a local fix · x skip · esc back",
  keysWorktree: "c edit message · C commit · p push · esc back",
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
  discussion: "discussion",
  assessment: "assessment",
  systemNote: "system",
  noPublication:
    "No publication is proposed. The reviewed discussion and rationale are shown above.",
  readOnly: "read-only · ↑/↓ scroll · ←/→ item · o browser · esc back",
  readOnlyShort: "no actions",
  scroll: "lines",
};

const ru: Strings = {
  title: "reviewmatic",
  target: "цель",
  verdict: "вердикт",
  items: "пункты публикации",
  pending: "ожидает",
  applied: "отправлено",
  replied: "ответ отправлен; статус не изменён",
  skipped: "пропущено",
  error: "ошибка",
  keysOverview: "↑/↓ выбор · enter открыть · q выход",
  keysDetail:
    "↑/↓ прокрутка · ←/→ пункт · o браузер · e правка · s только ответ · S ответ+статус · a локальный фикс · x пропустить · esc назад",
  keysWorktree: "c правка сообщения · C коммит · p пуш · esc назад",
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
  discussion: "дискуссия",
  assessment: "оценка",
  systemNote: "системное",
  noPublication: "Публикация не предлагается. Выше показаны проверенная дискуссия и обоснование.",
  readOnly: "только чтение · ↑/↓ прокрутка · ←/→ пункт · o браузер · esc назад",
  readOnlyShort: "без действий",
  scroll: "строки",
};

export function stringsFor(locale: string | null | undefined): Strings {
  return locale === "ru" ? ru : en;
}
