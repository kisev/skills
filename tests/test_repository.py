from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BUILT_SKILLS = ROOT / ".build" / "skills"
SKILLS_BINARY = subprocess.check_output(["mise", "which", "skills"], cwd=ROOT, text=True).strip()
PORTABLE_SKILLS = (
    "agents-md",
    "askme",
    "ast-grep",
    "commit-msg",
    "doit",
    "docs-prepare",
    "docs-review",
    "humanize",
    "project-spec",
    "rtk",
    "skill-improver",
    "stopit",
    "summary",
    "task-prepare",
    "task-review",
    "task-triage",
    "team-workflow",
    "walkthrough",
    "mr-prepare",
    "code-review",
    "release-prepare",
    "release-review",
    "mattermost",
    "attempt",
    "goal",
    "schedule",
    "usage",
    "overview",
    "lsp-report",
)
FORBIDDEN_PORTABLE_MARKERS = (
    "../..",
    "catalog.yml",
    "~/.config/opencode",
    "~/.local/state/opencode",
)
PROJECT_REFERENCES = (
    "references/requirements.md",
    "references/architecture.md",
    "references/interviewing.md",
    "references/onboarding.md",
    "references/consolidation.md",
    "references/adr.md",
    "references/auditing.md",
)
SPEC_TEMPLATE_READMES = (
    "templates/specs/README.md",
    "templates/specs/requirements/README.md",
    "templates/specs/requirements/functional/README.md",
    "templates/specs/requirements/interfaces/README.md",
    "templates/specs/requirements/quality/README.md",
    "templates/specs/requirements/constraints/README.md",
    "templates/specs/architecture/README.md",
    "templates/specs/architecture/01-introduction-and-goals/README.md",
    "templates/specs/architecture/02-architecture-constraints/README.md",
    "templates/specs/architecture/03-context-and-scope/README.md",
    "templates/specs/architecture/04-solution-strategy/README.md",
    "templates/specs/architecture/05-building-block-view/README.md",
    "templates/specs/architecture/06-runtime-view/README.md",
    "templates/specs/architecture/07-deployment-view/README.md",
    "templates/specs/architecture/08-crosscutting-concepts/README.md",
    "templates/specs/architecture/09-architecture-decisions/README.md",
    "templates/specs/architecture/10-quality-requirements/README.md",
    "templates/specs/architecture/11-risks-and-technical-debt/README.md",
    "templates/specs/architecture/12-glossary/README.md",
)
PROJECT_REFERENCE_CONTRACTS = {
    "references/requirements.md": "существующие id не перенумеровывай",
    "references/architecture.md": "дополнительные markdown-файлы разрешены только",
    "references/interviewing.md": "readiness check",
    "references/onboarding.md": "`known`",
    "references/consolidation.md": "consolidation: required",
    "references/adr.md": "не переписывай старый adr",
    "references/auditing.md": "`implementation_ahead`",
}
PROJECT_TEMPLATE_SECTIONS = (
    "## назначение",
    "## сюда относится",
    "## сюда не относится",
    "## правила декомпозиции",
    "## ожидаемая структура",
    "## шаблон содержания",
)
ADR_TEMPLATE_SECTIONS = (
    "## контекст и постановка проблемы",
    "## драйверы решения",
    "## рассмотренные варианты",
    "## итоговое решение",
    "## последствия",
    "## связи",
)
WORKFLOW_CONTRACTS = {
    "humanize": (
        "точные цитаты, код, вывод команд",
        "не подменяй роль автора ролью ревьюера",
    ),
    "summary": (
        "не добавляй фактов, которых нет в исходных данных",
        "строго различай текущую ситуацию, предложение, принятое решение",
    ),
    "commit-msg": (
        "git diff --cached",
        "выведи ровно одну строку",
        "не выполняй `git add`, `git commit`",
    ),
    "agents-md": (
        "до 20 однострочных пунктов",
        "покажи точный diff и получи явное подтверждение",
    ),
    "docs-prepare": (
        "один пользовательский документ diataxis",
        "content-addressed preview artifact",
    ),
    "docs-review": (
        "не изменяй репозиторий, документы, внешние системы",
        "сообщай только подтверждённые замечания",
    ),
    "project-spec": (
        "пользователь должен явно передать один режим",
        "`spec-init`",
        "`spec-onboard`",
        "`spec-update`",
        "`spec-audit`",
        "все 19 обязательных `readme.md`",
        "этот режим полностью read-only",
    ),
    "stopit": (
        "во временной директории ос, не в репозитории",
        "покажи полный черновик и временный путь",
    ),
    "doit": (
        "не выполняй push",
        "требуют отдельного подтверждения",
        "content-addressed preview artifact",
        "не требуй конкретный host",
    ),
    "goal": (
        "строго read-only",
        "work-item/v1",
        "не создавай",
        "не изменяй файлы",
        "не имитируй self-review",
        "не более 3000 символов",
    ),
    "walkthrough": (
        "не является ревью",
        "coverage.complete=false",
        "это карта чтения, а не оценка качества",
    ),
    "ast-grep": (
        "сначала всегда создай preview",
        "--apply --confirm <digest>",
        "не выполняй автоустановку",
    ),
    "skill-improver": (
        "ровно один существующий каталог",
        "<skill-improvement-complete>",
        "не commands, plugins, agents",
    ),
    "rtk": (
        "внешний cli, не устанавливаемый этим skill",
        "исходную команду напрямую",
        "не включай hook",
    ),
}
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
RUNNERS = {
    "ast-grep": "scripts/ast_grep.py",
    "rtk": "scripts/rtk.py",
    "skill-improver": "scripts/skill_improver.py",
    "walkthrough": "scripts/walkthrough.py",
    "task-triage": "scripts/triage_task.py",
    "task-review": "scripts/review_task.py",
    "task-prepare": "scripts/prepare_task.py",
    "mr-prepare": "scripts/prepare_mr.py",
    "code-review": "scripts/review_mr.py",
    "release-prepare": "scripts/prepare_release.py",
    "release-review": "scripts/review_release.py",
    "mattermost": "scripts/mattermost.py",
    "team-workflow": "scripts/team_workflow.py",
    "schedule": "scripts/schedule.py",
    "usage": "scripts/usage.py",
    "overview": "scripts/overview.py",
    "lsp-report": "scripts/lsp_report.py",
}


class PortableSkillValidationTests(unittest.TestCase):
    def test_all_portable_skills_have_required_frontmatter(self) -> None:
        for name in PORTABLE_SKILLS:
            skill = ROOT / "skills" / name / "SKILL.md"
            with self.subTest(skill=name):
                self.assertTrue(skill.is_file())
                lines = skill.read_text(encoding="utf-8").splitlines()
                self.assertEqual(lines[0], "---")
                end = lines.index("---", 1)
                fields = {
                    line.split(":", 1)[0]
                    for line in lines[1:end]
                    if line and not line.startswith(" ") and ":" in line
                }
                self.assertTrue(
                    {"name", "description", "license", "metadata"}.issubset(fields)
                )
                self.assertTrue(
                    fields.issubset(
                        {
                            "name",
                            "description",
                            "license",
                            "compatibility",
                            "metadata",
                            "allowed-tools",
                        }
                    )
                )
                self.assertEqual(lines[1], f"name: {name}")
                self.assertIn("license: MIT", lines)
                self.assertIn('  author: "Kirill Sevriugin"', lines)
                self.assertIn('  version: "1.1.1"', lines)
                metadata_start = lines.index("metadata:") + 1
                self.assertEqual(
                    lines[metadata_start:end],
                    ['  author: "Kirill Sevriugin"', '  version: "1.1.1"'],
                )

    def test_public_skill_and_repository_texts_are_russian(self) -> None:
        paths = [
            ROOT / "README.md",
            *(ROOT / "docs").rglob("*.md"),
            *(ROOT / "skills").rglob("*.md"),
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertRegex(path.read_text(encoding="utf-8"), CYRILLIC)
        for name in PORTABLE_SKILLS:
            lines = (
                (ROOT / "skills" / name / "SKILL.md")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            frontmatter_end = lines.index("---", 1)
            with self.subTest(skill=name, section="description"):
                self.assertRegex("\n".join(lines[1:frontmatter_end]), CYRILLIC)
            with self.subTest(skill=name, section="body"):
                self.assertRegex("\n".join(lines[frontmatter_end + 1 :]), CYRILLIC)

    def test_portable_workflows_preserve_source_contracts(self) -> None:
        for name, contracts in WORKFLOW_CONTRACTS.items():
            text = (
                (ROOT / "skills" / name / "SKILL.md")
                .read_text(encoding="utf-8")
                .lower()
            )
            for contract in contracts:
                with self.subTest(skill=name, contract=contract):
                    self.assertIn(contract, text)

    def test_referenced_resources_are_self_contained(self) -> None:
        resources = {
            "askme": ("references/question-guidelines.md",),
            "agents-md": ("references/agents-md-guidelines.md",),
            "project-spec": (
                *PROJECT_REFERENCES,
                "templates/adr.md",
                *SPEC_TEMPLATE_READMES,
            ),
        }
        for name, paths in resources.items():
            skill = BUILT_SKILLS / name
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            for relative in paths:
                with self.subTest(skill=name, resource=relative):
                    self.assertTrue((skill / relative).is_file())
                    if relative.startswith("references/"):
                        self.assertIn(relative, text)

    def test_interaction_contract_is_materialized_for_affected_skills(self) -> None:
        names = (
            "project-spec", "docs-prepare", "doit", "team-workflow", "task-triage",
            "task-review", "task-prepare", "mr-prepare", "code-review",
            "release-prepare", "release-review",
        )
        source = ROOT / "shared/references/interaction-contract.md"
        source_text = source.read_text(encoding="utf-8")
        for requirement in (
            "resolve -> prepare -> present -> confirm ->\napply -> report",
            "**Question** задавай только до `prepare`",
            "**Confirmation** запрашивай только после `prepare`",
            "Read-only collection, review и подготовка ручного плана\nне требуют Confirmation",
            "TLDR, scope, risks, checks",
            "content-addressed write-once artifact",
            "apply-команду с digest",
            "отклоняет отсутствующий,\nизменённый, stale, просроченный или уже использованный plan",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, source_text)
        for name in names:
            skill = BUILT_SKILLS / name
            destination = skill / "references/interaction-contract.md"
            with self.subTest(skill=name):
                self.assertEqual(destination.read_bytes(), source.read_bytes())
                self.assertIn("references/interaction-contract.md", (skill / "SKILL.md").read_text(encoding="utf-8"))
        for name in ("project-spec", "docs-prepare", "doit"):
            text = (BUILT_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=name, behavior="compact-preview"):
                self.assertIn("TLDR", text)
                self.assertIn("не печатай", text)

    def test_project_spec_has_complete_nineteen_file_contract(self) -> None:
        self.assertEqual(len(SPEC_TEMPLATE_READMES), 19)
        skill = ROOT / "skills/project-spec"
        self.assertTrue((skill / "templates/adr.md").is_file())
        for relative in SPEC_TEMPLATE_READMES:
            self.assertTrue((skill / relative).is_file(), relative)

    def test_project_spec_resources_preserve_semantic_guidance(self) -> None:
        skill = ROOT / "skills/project-spec"
        for relative, contract in PROJECT_REFERENCE_CONTRACTS.items():
            with self.subTest(resource=relative, contract=contract):
                self.assertIn(
                    contract, (skill / relative).read_text(encoding="utf-8").lower()
                )
        for relative in SPEC_TEMPLATE_READMES:
            text = (skill / relative).read_text(encoding="utf-8").lower()
            for section in PROJECT_TEMPLATE_SECTIONS:
                with self.subTest(template=relative, section=section):
                    self.assertIn(section, text)
        adr = (skill / "templates/adr.md").read_text(encoding="utf-8").lower()
        for section in ADR_TEMPLATE_SECTIONS:
            with self.subTest(template="templates/adr.md", section=section):
                self.assertIn(section, adr)

    def test_askme_remains_compatible_with_portable_contract(self) -> None:
        skill = ROOT / "skills/askme/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("references/question-guidelines.md", text)
        self.assertIn("Если у host нет такого инструмента, задай вопросы в чате.", text)
        self.assertIn("Если фактов достаточно", text)
        self.assertIn("`task-prepare`", text)
        self.assertIn("Не меняй репозиторий, внешние системы, документы", text)
        self.assertIn("Не запускай отдельный workflow без нового запроса", text)
        self.assertNotIn("native OpenCode", text)
        self.assertNotIn("../../", text)
        self.assertNotIn("Каталог", text)
        self.assertEqual(
            (BUILT_SKILLS / "askme/references/question-guidelines.md").read_bytes(),
            (ROOT / "shared/references/question-guidelines.md").read_bytes(),
        )

    def test_goal_is_prompt_only_and_preserves_materialized_contract(self) -> None:
        skill = BUILT_SKILLS / "goal"
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("work-item/v1", text)
        self.assertIn("3000", text)
        self.assertFalse((skill / "scripts/goal.py").exists())
        self.assertFalse((skill / "scripts/portable_runtime").exists())
        self.assertEqual(
            (skill / "scripts/work_item.py").read_bytes(),
            (ROOT / "shared/references/work_item.py").read_bytes(),
        )

    def test_goal_output_contract_declares_bounded_deterministic_outcomes(self) -> None:
        text = (ROOT / "skills/goal/SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "не более 3000 символов",
            "байт-в-байт тот же JSON",
            "статус premortem равен `skipped`",
            "при независимом проходе статус равен\n`completed`",
            "verdict `ready`",
            "blocker явным",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_python_runtime_is_exactly_materialized_for_each_runner(self) -> None:
        manifest = json.loads(
            (ROOT / "shared/manifest.json").read_text(encoding="utf-8")
        )
        runtime_entries = [
            entry
            for entry in manifest["files"]
            if entry["source"].startswith("references/python_runtime/")
        ]
        destinations = {entry["destination"] for entry in runtime_entries}
        for name in ("schedule", "usage", "overview", "lsp-report"):
            with self.subTest(skill=name):
                self.assertIn(f"{name}/scripts/portable_runtime/capabilities.py", destinations)
                self.assertIn(f"{name}/scripts/portable_runtime/contract.py", destinations)
        for entry in runtime_entries:
            source = ROOT / "shared" / entry["source"]
            destination = BUILT_SKILLS / entry["destination"]
            with self.subTest(destination=destination):
                self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_portable_skills_have_no_forbidden_dependencies(self) -> None:
        opencode_skills = {"attempt", "schedule", "usage", "overview", "lsp-report"}
        for path in BUILT_SKILLS.rglob("*"):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".md", ".py"}
            ):
                text = path.read_text(encoding="utf-8").lower()
                markers: tuple[str, ...] = FORBIDDEN_PORTABLE_MARKERS
                if path.relative_to(BUILT_SKILLS).parts[0] in opencode_skills:
                    markers = tuple(marker for marker in markers if marker not in {"~/.config/opencode", "~/.local/state/opencode"})
                for marker in markers:
                    self.assertNotIn(marker, text, f"{marker} in {path}")

    def test_gitlab_skills_materialize_their_own_contract_and_runtime(self) -> None:
        names = (
            "task-triage",
            "task-review",
            "task-prepare",
            "mr-prepare",
            "code-review",
            "release-prepare",
            "release-review",
        )
        for name in names:
            root = BUILT_SKILLS / name
            with self.subTest(skill=name):
                self.assertTrue((root / "references/gitlab-workflow.md").is_file())
                self.assertTrue((root / "scripts/portable_runtime/contract.py").is_file())
                self.assertEqual(
                    (root / "scripts/portable_runtime/contract.py").read_bytes(),
                    (ROOT / "shared/references/portable_gitlab/contract.py").read_bytes(),
                )
                self.assertEqual(
                    (root / "references/portable-gitlab-contracts-v2.md").read_bytes(),
                    (ROOT / "shared/references/portable_gitlab/contracts-v2.md").read_bytes(),
                )
                self.assertEqual(
                    (root / "references/portable-gitlab-contracts-v2.schema.json").read_bytes(),
                    (ROOT / "shared/references/portable_gitlab/artifact-contracts-v2.schema.json").read_bytes(),
                )

    def test_pinned_cli_lists_all_portable_skills(self) -> None:
        result = subprocess.run(
            [SKILLS_BINARY, "add", str(BUILT_SKILLS), "--list"],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in PORTABLE_SKILLS:
            self.assertIn(name, result.stdout)

    def test_pinned_cli_installs_each_skill_for_codex_and_opencode(self) -> None:
        for name in PORTABLE_SKILLS:
            for agent in ("codex", "opencode"):
                with self.subTest(skill=name, agent=agent):
                    self.assert_isolated_install(name, agent)

    def assert_isolated_install(self, name: str, agent: str) -> None:
        home = Path(tempfile.mkdtemp())
        checkout = home / "checkout"
        shutil.copytree(ROOT, checkout)
        environment = {
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
        }
        result = subprocess.run(
            [
                SKILLS_BINARY,
                "add",
                str(checkout / ".build/skills"),
                "--skill",
                name,
                "--agent",
                agent,
                "--copy",
                "--global",
                "--yes",
            ],
            cwd=home,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = home / ".agents/skills" / name
        self.assertTrue((installed / "SKILL.md").is_file())
        shutil.rmtree(checkout / "shared")
        shutil.rmtree(checkout)
        source = BUILT_SKILLS / name
        for path in source.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(source)
                self.assertEqual((installed / relative).read_bytes(), path.read_bytes())
        runner = RUNNERS.get(name)
        if runner is not None:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    str(installed / runner),
                    "--capabilities",
                ],
                cwd=tempfile.gettempdir(),
                env={**environment, "PYTHONPATH": "/invalid"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["schema_version"], 1)


class PortableRunnerTests(unittest.TestCase):
    def run_runner(
        self,
        name: str,
        *arguments: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "PYTHONPATH": "/invalid"}
        if env is not None:
            environment.update(env)
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                    str(BUILT_SKILLS / name / RUNNERS[name]),
                *arguments,
            ],
            cwd=tempfile.gettempdir(),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_every_runner_supports_help_and_capabilities_from_foreign_cwd(self) -> None:
        for name in RUNNERS:
            with self.subTest(skill=name, command="help"):
                help_result = self.run_runner(name, "--help")
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
            with self.subTest(skill=name, command="capabilities"):
                capabilities = self.run_runner(name, "--capabilities")
                self.assertEqual(capabilities.returncode, 0, capabilities.stderr)
                self.assertEqual(json.loads(capabilities.stdout)["schema_version"], 1)

    def test_external_cli_absence_returns_escalation_without_installing(self) -> None:
        for name, arguments in (
            ("ast-grep", ("search", "--lang", "python", "--pattern", "x", ".")),
            ("rtk", ("check",)),
        ):
            with self.subTest(skill=name):
                result = self.run_runner(name, *arguments, env={"PATH": "/nonexistent"})
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "escalate")

    def fake_ast_grep(self, directory: Path) -> Path:
        executable = directory / "ast-grep"
        executable.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import json
                import os
                import sys
                from pathlib import Path

                target = Path(sys.argv[-1])
                if os.environ.get("FAKE_EMPTY"):
                    print("[]")
                    raise SystemExit(1)
                if os.environ.get("FAKE_OUTSIDE"):
                    print(json.dumps([{{"file": os.environ["FAKE_OUTSIDE"], "replacement": "let value = 1", "replacementOffsets": {{"start": 0, "end": 16}}}}]))
                    raise SystemExit(0)
                rewrite = sys.argv[sys.argv.index("--rewrite") + 1] if "--rewrite" in sys.argv else None
                matches = []
                files = [target] if target.is_file() else sorted(target.rglob("*.js"))
                for source in files:
                    text = source.read_text(encoding="utf-8")
                    if text.startswith("const "):
                        item = {{"file": str(source), "range": {{"start": {{"line": 0}}, "end": {{"line": 1}}}}, "text": text.rstrip("\\n")}}
                        if rewrite is not None:
                            item.update({{"replacement": "let " + text[6:].rstrip(";\\n"), "replacementOffsets": {{"start": 0, "end": len(text.rstrip("\\n"))}}}})
                        matches.append(item)
                print(json.dumps(matches))
                """
            ),
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable

    def ast_arguments(self, root: Path, *extra: str) -> tuple[str, ...]:
        return (
            "rewrite",
            "--lang",
            "javascript",
            "--pattern",
            "const $A = $B",
            "--rewrite",
            "let $A = $B",
            "--workspace",
            str(root),
            *extra,
            str(root),
        )

    def test_ast_rewrite_preview_apply_and_stale_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            source = root / "sample.js"
            source.write_text("const value = 1;\n", encoding="utf-8")
            bin_dir = Path(temporary) / "bin"
            bin_dir.mkdir()
            self.fake_ast_grep(bin_dir)
            environment = {"PATH": str(bin_dir)}
            preview = self.run_runner(
                "ast-grep", *self.ast_arguments(root), env=environment
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            document = json.loads(preview.stdout)
            self.assertFalse(document["applied"])
            self.assertEqual(source.read_text(encoding="utf-8"), "const value = 1;\n")
            source.write_text("const changed = 1;\n", encoding="utf-8")
            stale = self.run_runner(
                "ast-grep",
                *self.ast_arguments(
                    root, "--apply", "--confirm", document["confirmation"]
                ),
                env=environment,
            )
            self.assertEqual(stale.returncode, 2)
            self.assertEqual(
                json.loads(stale.stdout)["error"]["code"], "digest_mismatch"
            )
            self.assertEqual(source.read_text(encoding="utf-8"), "const changed = 1;\n")
            fresh = self.run_runner(
                "ast-grep", *self.ast_arguments(root), env=environment
            )
            digest = json.loads(fresh.stdout)["confirmation"]
            applied = self.run_runner(
                "ast-grep",
                *self.ast_arguments(root, "--apply", "--confirm", digest),
                env=environment,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), "let changed = 1\n")

    def test_ast_search_accepts_upstream_empty_result_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bin_dir = Path(temporary) / "bin"
            bin_dir.mkdir()
            self.fake_ast_grep(bin_dir)
            result = self.run_runner(
                "ast-grep",
                "search",
                "--lang",
                "python",
                "--pattern",
                "missing",
                str(temporary),
                env={"PATH": str(bin_dir), "FAKE_EMPTY": "1"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [])

    def test_ast_rewrite_rejects_external_and_symlink_targets_without_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            source = root / "sample.js"
            source.write_text("const value = 1;\n", encoding="utf-8")
            outside = Path(temporary) / "outside.js"
            outside.write_text("const outside = 1;\n", encoding="utf-8")
            link = root / "link.js"
            link.symlink_to(outside)
            bin_dir = Path(temporary) / "bin"
            bin_dir.mkdir()
            self.fake_ast_grep(bin_dir)
            environment = {"PATH": str(bin_dir), "FAKE_OUTSIDE": str(outside)}
            rejected = self.run_runner(
                "ast-grep", *self.ast_arguments(root), env=environment
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), "const value = 1;\n")
            self.assertEqual(
                outside.read_text(encoding="utf-8"), "const outside = 1;\n"
            )
            symlink_input = self.run_runner(
                "ast-grep",
                *self.ast_arguments(root, str(link)),
                env={"PATH": str(bin_dir)},
            )
            self.assertEqual(symlink_input.returncode, 2)
            self.assertEqual(
                outside.read_text(encoding="utf-8"), "const outside = 1;\n"
            )

    def test_ast_atomic_replacement_rolls_back_after_failure(self) -> None:
        script = BUILT_SKILLS / "ast-grep/scripts/ast_grep.py"
        specification = spec_from_file_location("portable_ast_grep", script)
        if specification is None or specification.loader is None:
            self.fail("cannot load portable ast-grep module")
        module = module_from_spec(specification)
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "first.js", root / "second.js"
            first.write_text("first before", encoding="utf-8")
            second.write_text("second before", encoding="utf-8")
            replace = module.os.replace

            def fail_second(source: str | Path, destination: str | Path) -> None:
                if Path(source).name == "update-1" and Path(destination) == second:
                    raise OSError("simulated replacement failure")
                replace(source, destination)

            with (
                patch.object(module.os, "replace", side_effect=fail_second),
                self.assertRaises(OSError),
            ):
                module.atomic_replace(
                    [(first, b"first after"), (second, b"second after")]
                )
            self.assertEqual(first.read_text(encoding="utf-8"), "first before")
            self.assertEqual(second.read_text(encoding="utf-8"), "second before")

    def test_skill_improver_checks_agent_skills_without_host_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "demo"
            target.mkdir()
            (target / "SKILL.md").write_text(
                '---\nname: demo\ndescription: Демонстрационный Agent Skill.\nlicense: MIT\nmetadata:\n  author: "Test"\n  version: "1.0.0"\n---\n\n# Demo\n',
                encoding="utf-8",
            )
            valid = self.run_runner("skill-improver", "check", "--path", str(target))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertEqual(json.loads(valid.stdout)["issues"], [])
            (target / "SKILL.md").write_text(
                (target / "SKILL.md")
                .read_text(encoding="utf-8")
                .replace("license: MIT", "custom.entrypoint: path:scripts/missing.py"),
                encoding="utf-8",
            )
            rejected = self.run_runner("skill-improver", "check", "--path", str(target))
            self.assertEqual(rejected.returncode, 1)
            self.assertIn(
                "frontmatter-unsupported-field",
                {issue["rule"] for issue in json.loads(rejected.stdout)["issues"]},
            )

    def test_walkthrough_current_range_diff_file_and_chunk_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            for arguments in (
                ("init", "-q"),
                ("config", "user.email", "test@example.invalid"),
                ("config", "user.name", "Test"),
            ):
                subprocess.run(
                    ["git", *arguments], cwd=repository, check=True, capture_output=True
                )
            (repository / "api_schema.py").write_text(
                "def Contract():\n    return 1\n", encoding="utf-8"
            )
            (repository / "service.py").write_text(
                "from api_schema import Contract\n\ndef run():\n    return Contract()\n",
                encoding="utf-8",
            )
            (repository / "test_service.py").write_text(
                "def test_run():\n    pass\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "add", "."], cwd=repository, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-qm", "base"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "branch", "base"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            (repository / "api_schema.py").write_text(
                "def Contract():\n    return 2\n", encoding="utf-8"
            )
            (repository / "config.yaml").write_text(
                "permission: admin\n", encoding="utf-8"
            )
            (repository / "notes.txt").write_text("untracked\n", encoding="utf-8")
            current = self.run_runner(
                "walkthrough", "--repo-root", str(repository), "--chunk-size", "1"
            )
            self.assertEqual(current.returncode, 0, current.stderr)
            payload = json.loads(current.stdout)
            self.assertTrue(payload["coverage"]["complete"])
            self.assertEqual(payload["statistics"]["files"], 3)
            self.assertEqual(
                payload["coverage"]["files_clustered"],
                payload["coverage"]["files_total"],
            )
            partial = self.run_runner(
                "walkthrough",
                "--repo-root",
                str(repository),
                "--chunk-size",
                "1",
                "--chunk-index",
                "0",
            )
            self.assertEqual(partial.returncode, 0, partial.stderr)
            self.assertFalse(json.loads(partial.stdout)["coverage"]["complete"])
            partial_payload = json.loads(partial.stdout)
            self.assertEqual(
                partial_payload["coverage"]["uncovered_files"],
                partial_payload["coverage"]["files_total"]
                - partial_payload["coverage"]["files_clustered"],
            )
            subprocess.run(
                ["git", "add", "."], cwd=repository, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-qm", "change"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            ranged = self.run_runner(
                "walkthrough", "--repo-root", str(repository), "--range", "base..HEAD"
            )
            self.assertEqual(ranged.returncode, 0, ranged.stderr)
            artifact = repository / "review.diff"
            artifact.write_text(
                subprocess.run(
                    ["git", "diff", "HEAD^", "HEAD"],
                    cwd=repository,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout,
                encoding="utf-8",
            )
            from_file = self.run_runner(
                "walkthrough",
                "--repo-root",
                str(repository),
                "--diff-file",
                str(artifact),
            )
            self.assertEqual(from_file.returncode, 0, from_file.stderr)
            self.assertEqual(
                json.loads(from_file.stdout)["source"]["diff_file"], str(artifact)
            )


class OpenCodePortableRuntimeTests(unittest.TestCase):
    def run_skill(self, skill: str, *arguments: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        runner = RUNNERS[skill]
        return subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(BUILT_SKILLS / skill / runner), *arguments],
            cwd=tempfile.gettempdir(),
            env={**os.environ, **environment, "PYTHONPATH": "/invalid"},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_schedule_is_disabled_by_default_and_confirmation_is_single_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            state = Path(temporary) / "state"
            environment = {"HOME": temporary, "XDG_STATE_HOME": str(state)}
            preview = self.run_skill("schedule", "add", "--project", str(project), "--id", "morning", "--name", "Morning", "--schedule", "every: 1h", "--agent", "worker", "--model", "model", "--prompt", "inspect", environment=environment)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            token = json.loads(preview.stdout)["confirmation_request"]["id"]
            applied = self.run_skill("schedule", "add", "--project", str(project), "--id", "morning", "--name", "Morning", "--schedule", "every: 1h", "--agent", "worker", "--model", "model", "--prompt", "inspect", "--confirmation-id", token, environment=environment)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertFalse(json.loads(applied.stdout)["definition"]["enabled"])
            repeat = self.run_skill("schedule", "add", "--project", str(project), "--id", "morning", "--name", "Morning", "--schedule", "every: 1h", "--agent", "worker", "--model", "model", "--prompt", "inspect", "--confirmation-id", token, environment=environment)
            self.assertEqual(repeat.returncode, 2)

    def test_read_only_reports_do_not_create_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            state = Path(temporary) / "state"
            environment = {"HOME": temporary, "XDG_STATE_HOME": str(state), "XDG_CONFIG_HOME": str(Path(temporary) / "config")}
            for skill, arguments in (("usage", ("--project", str(project), "--format", "json")), ("overview", ("--project", str(project), "--format", "json")), ("lsp-report", ("--project", str(project), "--format", "json"))):
                result = self.run_skill(skill, *arguments, environment=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                json.loads(result.stdout)
                if skill in {"usage", "overview"}:
                    self.assertNotIn("goal", result.stdout)
                    self.assertNotIn("active_goals", result.stdout)
            self.assertFalse(state.exists())

    def test_historical_goal_state_is_not_current_overview_or_usage_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            state = Path(temporary) / "state/opencode/skills/goal"
            state.mkdir(parents=True)
            (state / "historical.json").write_text(json.dumps({"schema_version": 1, "goal_id": "historical", "status": "running", "project_root": str(project)}), encoding="utf-8")
            environment = {"HOME": temporary, "XDG_STATE_HOME": str(Path(temporary) / "state"), "XDG_CONFIG_HOME": str(Path(temporary) / "config")}
            for skill, arguments in (("usage", ("--project", str(project), "--format", "json")), ("overview", ("--project", str(project), "--format", "json"))):
                result = self.run_skill(skill, *arguments, environment=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("historical", result.stdout)
                self.assertNotIn("active_goals", result.stdout)
            self.assertTrue(state.joinpath("historical.json").is_file())


if __name__ == "__main__":
    unittest.main()
