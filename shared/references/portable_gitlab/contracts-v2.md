# Контракты private GitLab artifacts v2

Все новые evidence snapshots, publication plans, analysis reports, critic receipts,
review decisions, release readiness и finalize reports являются immutable
content-addressed JSON envelope `portable-gitlab/<kind>/v2`. Они хранятся только в
private state с правами `0700` для каталогов и `0600` для файлов. SHA-256 stdout
относится к полному envelope, а не к изменяемому указателю collection state.

Collection identity одинакова для всех профилей: `hostname`, resolved GitLab
`project_id`, object kind и IID. Profile записывается как producer и ограничивает
допустимую операцию, но не создаёт отдельного owner или collection.

`evidence_snapshot` фиксирует exact `base_sha`, `start_sha`, `head_sha` для MR и
completeness каждого компонента. `publication_plan` связывается с digest evidence
и содержит Markdown только для ручной публикации. `critic_receipt` связывается с
digest evidence и содержит независимые `run_id` и `session_id`.

`review_decision` содержит responses для всех primary/critic findings и
unresolved threads: `accept` или `reject` и непустую причину. `release_readiness`
связывает range/SHA, SemVer, compatibility, migration, rollback и CI gates.

v1 artifacts допустимо читать и использовать только для finalize совместимого
старого workflow. Их нельзя автоматически мигрировать, перезаписывать или
использовать как новый v2 artifact.
