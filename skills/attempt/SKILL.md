---
name: attempt
description: Читать состояние и безопасно отменять durable Background Attempts через OpenCode package tool.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and @kisev/skills-opencode background-attempts plugin.
allowed-tools: native Question, background_attempts
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.1"
---

# Attempt

`background_attempts` является единственным владельцем queue, dispatch, child
session, worktree и durable state. Skill не создаёт свой lifecycle и не выбирает
agent/model.

Допустимые статусы: `queued`, `running`, `waiting`, `completed`, `failed`,
`cancelled`, `orphaned`. Только четыре последних статуса terminal. `list` читает
summary текущей parent session/project, `status` показывает exact record, а
`result` читает structured result только после terminal transition.

Перед cancel прочитай status, покажи `attempt_id`, revision, status, child session
и workspace. Запроси native Question, затем передай exact `attempt_id`,
`expected_revision` и `expected_status`. Terminal attempt возвращает no-op;
stale revision/status, отказ пользователя и unconfirmed abort не удаляют state,
transcript, evidence или workspace.
