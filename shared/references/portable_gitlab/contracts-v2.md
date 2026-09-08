# Контракты private GitLab artifacts v2

Все новые evidence snapshots, publication plans, analysis reports, critic receipts,
review decisions, release readiness и finalize reports являются immutable
content-addressed JSON envelope `portable-gitlab/<kind>/v2`. Они хранятся только в
private state с правами `0700` для каталогов и `0600` для файлов. SHA-256 stdout
относится к полному envelope, а не к изменяемому указателю collection state.

Collection identity одинакова для всех профилей: `hostname`, resolved GitLab
`project_id`, object kind и IID. Profile записывается как producer и ограничивает
допустимую операцию, но не создаёт отдельного owner или collection.

Canonical schema проверяет envelope и payload каждого kind, запрещает неизвестные
поля и несовместимые пары kind/payload. Каждый payload фиксирует
`external_mutations=false`. `evidence_snapshot` фиксирует exact
`base_sha`, `start_sha`, `head_sha` для MR и completeness каждого компонента.
`local_wip_snapshot` хранит ref и committed, staged, unstaged, untracked sections.
`publication_plan` связывается с digest evidence и содержит Markdown только для
ручной публикации. `analysis_report` и `critic_receipt` связываются с digest
evidence и содержат `run_id`, `session_id` и findings.

`finalize_report` содержит exact digest и fingerprint evidence. `review_decision`
связывается с digest этого свежего report, фиксирует review mode и содержит disposition для всех
primary/critic findings и unresolved threads: `accept` или `reject` и непустую
причину. Старый finalize artifact не обходит повторную GET-only freshness check.
`release_readiness` связывает range/SHA, SemVer, compatibility, migration,
rollback и CI gates; `ready` допустим только при complete evidence и всех закрытых
gates.

v1 artifacts допустимо читать и использовать только для finalize совместимого
старого workflow. Их нельзя автоматически мигрировать, перезаписывать или
использовать как новый v2 artifact.
