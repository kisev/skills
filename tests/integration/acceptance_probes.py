"""Minimal live probe registry for the skill acceptance umbrella.

Every entry is one behavioral eval scenario for exactly one skill: the probe
engine installs only that skill into an isolated host sandbox, seeds the
fixture files, and asks one real model session to produce a small artifact.
The checks are machine-only (demanded section headers, grounded fixture
facts, answer contract), so a probe is honest minimal live coverage, never a
model self-report.

A skill lands here only when a fixture probe is meaningful. Skills whose
value cannot be exercised on a synthetic fixture are listed in SKIPS with the
explicit reason that the umbrella report prints verbatim.
"""

from __future__ import annotations

from typing import Any

AnswerContract = dict[str, Any]

COMMON_TAIL = (
    "Then write a JSON object with exactly one key to {answer}:\n"
    "- artifact: the absolute path of the artifact file you wrote\n"
    "Rules: use only the installed skill as your method; do not access the network; "
    "do not modify any file other than the artifact; do not ask questions in chat; "
    "write every demanded section header exactly as spelled."
)


def _standard(prompt_body: str) -> str:
    return f"{prompt_body}\nWrite the artifact to {{artifact}}.\n{COMMON_TAIL}"


# Skills a synthetic fixture cannot exercise meaningfully; the umbrella skips
# them with these reasons instead of faking green coverage.
SKIPS: dict[str, str] = {
    "ast-grep": (
        "the skill drives the ast-grep CLI, which the acceptance host does not pin; "
        "a sandbox run would exercise a missing binary, not the skill"
    ),
    "rtk": (
        "the skill drives the pinned rtk CLI, which is not installed in the isolated "
        "host sandbox; a probe would test the absence, not the skill"
    ),
    "taskmatic": (
        "the skill operates the taskmatic board service and its database; the "
        "acceptance sandbox has no board service by design"
    ),
    "skill-doctor": (
        "the skill diagnoses real recorded sessions; a fixture session would test "
        "the fixture, not the diagnosis method"
    ),
    "release-prepare": (
        "the skill requires a release inventory (tags, changelog, version "
        "authorities) and publication commands; the corpus golden pairs cover its "
        "contract offline and a fixture probe would imitate release state"
    ),
    "release-review": (
        "the skill reviews a release merge request with labels, SemVer, and "
        "publication commands against a real GitLab; no synthetic fixture can "
        "carry that state meaningfully"
    ),
}

PROBES: dict[str, dict[str, Any]] = {
    "agents-md": {
        "fixture": {
            "README.md": "# Demo tool\nA small CLI that renames log files by date.\n",
            "src/app.py": "def main() -> None:\n    print('renaming logs')\n",
            "tests/test_app.py": "def test_main() -> None:\n    main()\n",
        },
        "prompt": _standard(
            "This workspace is a tiny repository (README.md, src/app.py, "
            "tests/test_app.py). Prepare repository-scoped agent guidance for it: "
            "the artifact must carry the sections '## Project rules' and '## Commands', "
            "name the src/app.py entry point, and give the pytest command for the tests."
        ),
        "checks": {"contains": ["## Project rules", "## Commands", "app.py", "pytest"]},
        "timeout": 480,
    },
    "asd-ste100": {
        "fixture": {
            "input.txt": (
                "Prior to initiating the shutdown sequence, the operator shall ensure "
                "that the utilization of the auxiliary pressurization apparatus has "
                "been terminated. Failure to comply may result in the inadvertent "
                "activation of the emergency depressurization mechanism.\n"
            ),
        },
        "prompt": _standard(
            "input.txt holds a technical procedure paragraph. Simplify it with the "
            "installed skill: one action per instruction, direct wording, consistent "
            "terms. Keep the meaning about the auxiliary pressurization apparatus and "
            "the shutdown sequence. The artifact must contain exactly one section "
            "header, '## Simplified text', followed by the rewritten text and nothing "
            "else. Do not use the words 'utilization', 'initiating', 'inadvertent', "
            "or 'comply'."
        ),
        "checks": {
            "contains": ["## Simplified text", "pressurization"],
            "not_contains": ["utilization", "inadvertent"],
        },
        "timeout": 480,
    },
    "askme": {
        "fixture": {
            "request.txt": (
                "We need to improve the importer. Sometimes it is slow and sometimes "
                "it loses records. Budget is unclear. Make a proposal.\n"
            ),
        },
        "prompt": (
            "You are running the acceptance fixture for the installed askme skill. "
            "request.txt holds an ambiguous task. Follow the askme method, but this "
            "session cannot be interactive: instead of asking in chat, record the "
            "clarification in the artifact. The artifact must be a JSON array of 2 to 4 "
            "question objects; every object has exactly the keys 'question' and "
            "'options', and 'options' is an array of 2 to 4 short answer strings.\n"
            "Write the artifact to {artifact}.\n"
            "Then write a JSON object with exactly one key to {answer}:\n"
            "- artifact: the absolute path of the artifact file you wrote\n"
            "Rules: use only the installed skill as your method; do not access the "
            "network; do not modify any file other than the artifact."
        ),
        "checks": {
            "answer_keys": ["artifact"],
            "json_list": {"min": 2, "max": 4, "item_keys": ["question", "options"]},
        },
        "timeout": 480,
    },
    "briefing": {
        "fixture": {
            "notes.txt": (
                "Standup notes 2026-10-09: The importer migration finished on Tuesday. "
                "Latency dropped from 900ms to 240ms. The dashboard refresh job still "
                "fails on weekends. Alice owns the follow-up.\n"
            ),
        },
        "prompt": _standard(
            "notes.txt holds raw meeting notes. Summarize them with the installed "
            "skill without new research. The artifact must have the sections "
            "'## Summary' and '## Open items', mention the 240ms latency figure, and "
            "name Alice as the owner. Do not invent facts that are not in the notes."
        ),
        "checks": {
            "contains": ["## Summary", "## Open items", "240ms", "Alice"],
        },
        "timeout": 480,
    },
    "code-explain": {
        "fixture": {
            "diff.patch": (
                "--- a/src/parse.py\n+++ b/src/parse.py\n@@ -1,4 +1,6 @@\n"
                "def parse(line):\n-    return line.split(',')\n+    parts = line.split(',')\n"
                "+    if len(parts) != 3:\n+        raise ValueError('bad record')\n"
                "+    return parts\n"
            ),
        },
        "prompt": _standard(
            "diff.patch is the diff under review. Explain the change with the "
            "installed skill for a reader who knows the codebase. The artifact must "
            "have the sections '## What changed', '## Why it matters', and '## "
            "Risks', and must name src/parse.py and the parse function."
        ),
        "checks": {
            "contains": ["## What changed", "## Why it matters", "## Risks", "parse"],
        },
        "timeout": 480,
    },
    "code-simplify": {
        "fixture": {
            "snippet.py": (
                "def total(items):\n"
                "    result = 0\n"
                "    for index in range(len(items)):\n"
                "        result = result + items[index]\n"
                "    return result\n"
            ),
        },
        "prompt": _standard(
            "snippet.py holds the code to simplify. Apply the installed skill's "
            "prevention ladder and report, report-only, what should change. The "
            "artifact must have the sections '## Findings' and '## SIMPLIFY debt', "
            "and every finding line must carry exactly one tag from "
            "delete/stdlib/native/reuse/yagni/shrink."
        ),
        "checks": {
            "contains": ["## Findings", "## SIMPLIFY debt", "stdlib"],
        },
        "timeout": 480,
    },
    "commit-msg": {
        "fixture": {
            "diff.txt": (
                "diff --git a/src/worker.py b/src/worker.py\n"
                "--- a/src/worker.py\n+++ b/src/worker.py\n@@ -10,7 +10,8 @@\n"
                "     def retry(task):\n"
                "-        for attempt in range(3):\n"
                "+        for attempt in range(5):\n"
                "+        log.debug('retry %s', attempt)\n"
            ),
        },
        "prompt": _standard(
            "diff.txt is a staged change that raises the retry limit and logs each "
            "attempt. Write one commit message with the installed skill. The first "
            "line must be a conventional commit subject of at most 72 characters; the "
            "artifact may add a body after a blank line."
        ),
        "checks": {
            "first_line_regex": r"^(feat|fix|chore|docs|refactor|test|perf|ci|style|build)(\([\w./-]+\))?(!)?: \S.*",
            "first_line_max": 72,
        },
        "timeout": 480,
    },
    "debugging": {
        "fixture": {
            "report.txt": (
                "Command: python3 tools/convert.py data.csv\n"
                "Error: IndexError: list index out of range at tools/convert.py:12\n"
                "The script fails on the first row of every second file.\n"
            ),
        },
        "prompt": _standard(
            "report.txt describes a reproducible failure of python3 tools/convert.py. "
            "Apply the installed skill's method to what is observable in the report "
            "only (you cannot run the script). The artifact must have the sections "
            "'## Reproduction', '## Hypotheses', and '## Next test'; '## Hypotheses' "
            "must list at least three falsifiable hypotheses ranked by likelihood."
        ),
        "checks": {
            "contains": ["## Reproduction", "## Hypotheses", "## Next test", "convert.py"],
        },
        "timeout": 480,
    },
    "docs-prepare": {
        "fixture": {
            "change.txt": (
                "Behavior change: the importer now defaults --dry-run to true. The "
                "how-to page docs/importer.md still documents the old default.\n"
            ),
            "docs/importer.md": "# Importer how-to\nRun the importer with --dry-run false to write.\n",
        },
        "prompt": _standard(
            "change.txt authorizes a documentation update for the described behavior "
            "change. Apply the installed skill. The artifact must have the sections "
            "'## Affected documents', '## Required updates', and '## Preservation "
            "notes', and must name docs/importer.md and the new dry-run default."
        ),
        "checks": {
            "contains": ["## Affected documents", "## Required updates", "importer.md", "dry-run"],
        },
        "timeout": 480,
    },
    "docs-review": {
        "fixture": {
            "page.md": (
                "# Deployment\n1. Run the script.\n2. Wait some time.\n"
                "3. If it fails, see the troubleshooting page (does not exist).\n"
            ),
        },
        "prompt": _standard(
            "page.md is the user documentation under review; it references a "
            "troubleshooting page that does not exist and its step 2 is vague. Review "
            "it with the installed skill. The artifact must have the sections '## "
            "Accuracy', '## Completeness', '## Usability', and '## Verdict', and each "
            "finding must name the step or line it concerns."
        ),
        "checks": {
            "contains": [
                "## Accuracy",
                "## Completeness",
                "## Usability",
                "## Verdict",
                "troubleshooting",
            ],
        },
        "timeout": 480,
    },
    "eli5": {
        "fixture": {
            "topic.txt": (
                "Explain simply for a non-specialist: how a git rebase rewrites "
                "commit history. Audience has never used version control.\n"
            ),
        },
        "prompt": _standard(
            "topic.txt names the concept to explain. Explain it with the installed "
            "skill for that exact audience. The artifact must have the sections '## "
            "The idea', '## A everyday analogy', and '## What to remember'. Do not "
            "use the jargon words 'hash', 'reflog', or 'detached HEAD'."
        ),
        "checks": {
            "contains": ["## The idea", "## What to remember", "rebase"],
            "not_contains": ["reflog", "detached HEAD"],
        },
        "timeout": 480,
    },
    "goal": {
        "fixture": {
            "idea.txt": (
                "Feature idea: add a --since flag to the report command so users can "
                "filter events by date. Motivation: monthly audits. Constraints: must "
                "stay under the 4000-character goal limit, must name measurable "
                "acceptance criteria.\n"
            ),
        },
        "prompt": _standard(
            "idea.txt holds the feature idea. Prepare the executor goal with the "
            "installed skill. The artifact must have the sections '## Problem', '## "
            "Outcome', '## Acceptance criteria', and '## Scope', and the whole "
            "artifact must stay at most 4000 characters."
        ),
        "checks": {
            "contains": ["## Problem", "## Outcome", "## Acceptance criteria", "## Scope"],
            "max_chars": 4000,
        },
        "timeout": 480,
    },
    "handoff": {
        "fixture": {
            "session.txt": (
                "Session summary: migrated the importer to streaming reads; the "
                "open question is whether weekend jobs need the same backoff; the "
                "next step is measuring the queue depth under load.\n"
            ),
        },
        "prompt": _standard(
            "session.txt summarizes a finished work session. Prepare the handoff "
            "with the installed skill. The artifact must have the sections '## "
            "State', '## Decisions', '## Next steps', and '## Blockers', and '## "
            "Next steps' must mention measuring the queue depth."
        ),
        "checks": {
            "contains": ["## State", "## Decisions", "## Next steps", "## Blockers", "queue depth"],
        },
        "timeout": 480,
    },
    "humanize": {
        "fixture": {
            "draft.txt": (
                "Leveraging our robust, cutting-edge pipeline, we were able to "
                "successfully facilitate the seamless ingestion of data — moreover, "
                "it is important to note that the utilization of streaming reads "
                "delves into unparalleled performance enhancements.\n"
            ),
        },
        "prompt": _standard(
            "draft.txt is stiff AI-sounding prose. Edit it with the installed skill "
            "into direct natural language while preserving the meaning and the exact "
            "tokens 'streaming reads' and 'ingestion'. The artifact must be the "
            "edited text only, with no section headers and no em dashes."
        ),
        "checks": {
            "contains": ["streaming reads", "ingestion"],
            "not_contains": ["delve", "unparalleled", "\u2014", "Leveraging"],
        },
        "timeout": 480,
    },
    "slides-prompts-prepare": {
        "fixture": {
            "brief.txt": (
                "Theme: deep-sea exploration. Team facts: five engineers, one "
                "submersible, sonar mapping since 2024. Slide: the mapping "
                "technology overview.\n"
            ),
        },
        "prompt": _standard(
            "brief.txt names the presentation theme, the factual team references, "
            "and one slide subject. Prepare the image prompt for that slide with the "
            "installed skill. The artifact must have the sections '## Prompt' and '## "
            "Factual anchors', the '## Prompt' section must be a single image "
            "generation prompt mentioning the deep-sea theme, and '## Factual "
            "anchors' must stay inside the given facts."
        ),
        "checks": {
            "contains": ["## Prompt", "## Factual anchors", "deep-sea"],
        },
        "timeout": 480,
    },
    "spec-manage": {
        "fixture": {
            "change.txt": (
                "Authorized behavior change: the report command gains a --since flag "
                "(dates in UTC, default: all events). specs/report.md documents the "
                "command contract.\n"
            ),
            "specs/report.md": "# Report contract\nThe report command prints all events.\n",
        },
        "prompt": _standard(
            "change.txt authorizes updating the agreed contract in specs/report.md. "
            "Apply the installed skill to the fixture only. The artifact must have "
            "the sections '## Canonical change', '## Materialized updates', and '## "
            "Compatibility', must name specs/report.md and the --since flag, and "
            "'## Compatibility' must state that the default output stays unchanged."
        ),
        "checks": {
            "contains": [
                "## Canonical change",
                "## Materialized updates",
                "## Compatibility",
                "--since",
            ],
        },
        "timeout": 480,
    },
    "task-prepare": {
        "fixture": {
            "agreements.txt": (
                "Call 2026-10-10: we agreed to split the importer migration into a "
                "pilot and a rollout. The pilot covers one region. The rollout needs "
                "a GitLab task with acceptance criteria. Owner: the platform team.\n"
            ),
        },
        "prompt": _standard(
            "agreements.txt records what was agreed. Prepare the GitLab task with "
            "the installed skill. The artifact must have the sections '## Title', '## "
            "Description', '## Acceptance criteria', and '## Publication', and '## "
            "Publication' must contain one ready-to-run glab command that creates the "
            "issue."
        ),
        "checks": {
            "contains": [
                "## Title",
                "## Description",
                "## Acceptance criteria",
                "## Publication",
                "glab",
            ],
        },
        "timeout": 480,
    },
    "task-review": {
        "fixture": {
            "task.txt": (
                "Task: Improve the importer. Description: make it better and faster. "
                "Acceptance criteria: it should work well. Milestone: v2.\n"
            ),
        },
        "prompt": _standard(
            "task.txt is the work item under review. Review it with the installed "
            "skill for semantic quality. The artifact must have the sections '## "
            "Verdict', '## Risks', and '## Required rework', the '## Verdict' must be "
            "one of ready/not_ready, and the rework list must say what concrete "
            "acceptance criterion is missing."
        ),
        "checks": {
            "contains": ["## Verdict", "## Risks", "## Required rework", "not_ready"],
        },
        "timeout": 480,
    },
    "task-triage": {
        "fixture": {
            "issue.json": (
                '{"iid": 42, "title": "Importer loses records on retry", '
                '"labels": ["bug", "importer"], "state": "opened", '
                '"description": "Every retry after a timeout drops the batch. Two '
                "duplicate reports reference the nightly job.\\n"
                'Started after the streaming migration."}'
            ),
        },
        "prompt": _standard(
            "issue.json is the GitLab issue to triage. Triage it with the installed "
            "skill. The artifact must have the sections '## Analysis', '## "
            "Milestone', '## Priority', and '## Dependencies', '## Priority' must be "
            "one of high/medium/low, and '## Dependencies' must name the streaming "
            "migration as the suspected origin."
        ),
        "checks": {
            "contains": [
                "## Analysis",
                "## Milestone",
                "## Priority",
                "## Dependencies",
                "streaming",
            ],
        },
        "timeout": 480,
    },
    "tdd": {
        "fixture": {
            "calc.py": "def add(a, b):\n    return a + b\n",
            "test_calc.py": (
                "from calc import add, subtract\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n"
                "def test_subtract():\n    assert subtract(5, 2) == 3\n"
            ),
            "check.sh": '#!/bin/sh\ncd "$(dirname "$0")" && python3 test_calc.py\n',
        },
        "prompt": _standard(
            "This workspace holds a tiny code base and a failing test run: "
            "`python3 test_calc.py` fails because subtract is missing. Drive the "
            "red-green cycle with the installed skill: confirm the red run, add the "
            "minimal implementation to calc.py, and make `python3 test_calc.py` pass. "
            "Do not add features beyond subtract. The artifact must have the sections "
            "'## Red' (the observed failing output) and '## Green' (the passing run "
            "output), quoting the real command output of both runs."
        ),
        "checks": {
            "contains": ["## Red", "## Green", "subtract"],
            "rerun": ["python3", "test_calc.py"],
        },
        "timeout": 600,
    },
    "team-1on1": {
        "fixture": {
            "context.txt": (
                "Report: Dana. Journal: Dana promised to deliver the import dry-run "
                "on Oct 5 (still open); last 1:1 was six weeks ago. Recent work: the "
                "migration pilot went green.\n"
            ),
        },
        "prompt": _standard(
            "context.txt is the private team context for a 1:1 with Dana. Prepare "
            "the 1:1 with the installed skill. The artifact must have the sections "
            "'## Open commitments', '## Agenda', and '## Follow-ups', and '## Open "
            "commitments' must list the dry-run promise with its age."
        ),
        "checks": {
            "contains": ["## Open commitments", "## Agenda", "## Follow-ups", "dry-run"],
        },
        "timeout": 480,
    },
    "team-agreements": {
        "fixture": {
            "chat.txt": (
                "2026-10-10 14:02 Dana: we ship the pilot on Friday\n"
                "2026-10-10 14:03 Lee: I will write the rollback note\n"
                "2026-10-10 14:05 Dana: Lee, also freeze the schema until Monday\n"
            ),
        },
        "prompt": _standard(
            "chat.txt is the conversation that just ended. Record its agreements "
            "with the installed skill. The artifact must have the sections '## "
            "Agreements' and '## Open per person'; every agreement line must carry "
            "its date, and '## Open per person' must separate what Lee owes from what "
            "Dana owes."
        ),
        "checks": {
            "contains": ["## Agreements", "## Open per person", "Lee", "rollback"],
        },
        "timeout": 480,
    },
    "team-feedback": {
        "fixture": {
            "situation.txt": (
                "Dana merged to main twice this week without the agreed review gate. "
                "Both merges were small. The gate exists to keep main releasable.\n"
            ),
        },
        "prompt": _standard(
            "situation.txt describes what happened. Prepare the feedback conversation "
            "with the installed skill. The artifact must have the sections '## "
            "Observation', '## Impact', and '## Request'; the observation must stay "
            "factual, and the request must name the review gate explicitly."
        ),
        "checks": {
            "contains": ["## Observation", "## Impact", "## Request", "review gate"],
        },
        "timeout": 480,
    },
    "team-health": {
        "fixture": {
            "signals.txt": (
                "Quarter signals: 1:1 cadence held for 2 of 5 reports; open "
                "commitments older than 30 days: 4; feedback given: 2 critical, 0 "
                "recognizing; delivery load: two releases in one week.\n"
            ),
        },
        "prompt": _standard(
            "signals.txt holds the quarter's journal signals. Review team health "
            "with the installed skill. The artifact must have the sections '## "
            "Cadence', '## Commitments', '## Feedback balance', and '## "
            "Recommendations', and every recommendation must trace to one named "
            "signal."
        ),
        "checks": {
            "contains": [
                "## Cadence",
                "## Commitments",
                "## Feedback balance",
                "## Recommendations",
            ],
        },
        "timeout": 480,
    },
    "team-incident": {
        "fixture": {
            "incident.txt": (
                "2026-10-09 09:00 the nightly import started\n"
                "2026-10-09 09:20 the queue depth exceeded the limit and the job "
                "was killed\n2026-10-09 11:00 service restored by re-running with a "
                "smaller batch\nContributing: the batch size came from an unreviewed "
                "config change.\n"
            ),
        },
        "prompt": _standard(
            "incident.txt holds the incident timeline. Facilitate the postmortem "
            "with the installed skill. The artifact must have the sections '## "
            "Timeline', '## Impact', '## Contributing factors', and '## Action "
            "items'; the timeline must use the given timestamps, and the "
            "contributing factors must be blameless (no person as the cause)."
        ),
        "checks": {
            "contains": [
                "## Timeline",
                "## Impact",
                "## Contributing factors",
                "## Action items",
                "batch",
            ],
        },
        "timeout": 480,
    },
    "team-onboarding": {
        "fixture": {
            "team.txt": (
                "Team context: the platform team owns the importer and the report "
                "CLI. Delivery: two-week release cadence. New member: Sam, starts "
                "Monday, first task is the report CLI.\n"
            ),
        },
        "prompt": _standard(
            "team.txt is the team context; Sam starts Monday. Prepare the onboarding "
            "pack with the installed skill. The artifact must have the sections '## "
            "Onboarding pack', '## First weeks', and '## Contacts', and '## First "
            "weeks' must start with the report CLI task."
        ),
        "checks": {
            "contains": ["## Onboarding pack", "## First weeks", "## Contacts", "report CLI"],
        },
        "timeout": 480,
    },
    "team-people": {
        "fixture": {
            "journal.txt": (
                "Journal: Dana promised the import dry-run on Oct 5 (no update). "
                "Lee closed the rollback note. Upcoming: the schema freeze ends "
                "Monday.\n"
            ),
        },
        "prompt": _standard(
            "journal.txt holds durable outcomes. Maintain the people context with "
            "the installed skill. The artifact must have the sections '## Profile "
            "updates', '## Open commitments', and '## Reviewed this week'; '## Open "
            "commitments' must show the dry-run promise as still open."
        ),
        "checks": {
            "contains": [
                "## Profile updates",
                "## Open commitments",
                "## Reviewed this week",
                "dry-run",
            ],
        },
        "timeout": 480,
    },
    "team-performance": {
        "fixture": {
            "facts.txt": (
                "Facts: Dana delivered the migration pilot green two weeks early, "
                "wrote the rollback runbook, and mentored Sam on the report CLI. "
                "Growth area: Dana wants deeper database internals practice.\n"
            ),
        },
        "prompt": _standard(
            "facts.txt holds journal facts about Dana. Prepare the quarterly "
            "performance summary with the installed skill. The artifact must have the "
            "sections '## Performance summary', '## Evidence', and '## Growth plan'; "
            "every summary claim must cite a fact, and the growth plan must follow "
            "the stated growth area."
        ),
        "checks": {
            "contains": ["## Performance summary", "## Evidence", "## Growth plan", "rollback"],
        },
        "timeout": 480,
    },
    "team-report": {
        "fixture": {
            "delivery.txt": (
                "Quarter delivery: importer migration shipped; latency 900ms to "
                "240ms; two releases; the dashboard refresh job still fails on "
                "weekends (open).\n"
            ),
        },
        "prompt": _standard(
            "delivery.txt is the quarter's delivery evidence. Prepare the "
            "stakeholder-facing quarterly report with the installed skill. The "
            "artifact must have the sections '## Roll-up', '## Demo theses', and '## "
            "Open risks'; every thesis must be one sentence, and the weekend job "
            "failure must appear under open risks."
        ),
        "checks": {
            "contains": ["## Roll-up", "## Demo theses", "## Open risks", "weekend"],
        },
        "timeout": 480,
    },
    "team-retro": {
        "fixture": {
            "evidence.txt": (
                "Delivery evidence: 12 merged changes, 1 reverted; reviews took a "
                "median 6 hours; the release froze twice for missed acceptance "
                "criteria; retro survey: 'too many parallel branches'.\n"
            ),
        },
        "prompt": _standard(
            "evidence.txt holds the retro evidence. Prepare the retrospective with "
            "the installed skill. The artifact must have the sections '## Evidence', "
            "'## Themes', '## Actions', and '## Owners'; every action must trace to "
            "named evidence, and every action must carry one owner."
        ),
        "checks": {
            "contains": ["## Evidence", "## Themes", "## Actions", "## Owners"],
        },
        "timeout": 480,
    },
    "team-roadmap": {
        "fixture": {
            "profile.txt": (
                "Team profile: platform team, five engineers. Delivery evidence: the "
                "importer migration shipped; the report CLI adoption is at 40%; the "
                "next stated goal is cutting review latency in half.\n"
            ),
        },
        "prompt": _standard(
            "profile.txt holds the team profile and delivery evidence. Review and "
            "update the roadmap with the installed skill. The artifact must have the "
            "sections '## Roadmap', '## Evidence', and '## Open questions'; every "
            "roadmap item must cite its evidence, and no item may invent a goal that "
            "the evidence does not support."
        ),
        "checks": {
            "contains": ["## Roadmap", "## Evidence", "## Open questions", "review latency"],
        },
        "timeout": 480,
    },
    "team-sprint-close": {
        "fixture": {
            "sprint.txt": (
                "Sprint 41 context: planned the importer pilot, the report CLI "
                "onboarding, and the schema freeze. Done: pilot shipped, onboarding "
                "done. Not done: the schema freeze is still open; the rollback note "
                "moved to next sprint.\n"
            ),
        },
        "prompt": _standard(
            "sprint.txt holds the sprint context. Close the sprint with the "
            "installed skill. The artifact must have the sections '## Completed', '## "
            "Carry-over', and '## Verified by'; '## Carry-over' must name the schema "
            "freeze and the rollback note."
        ),
        "checks": {
            "contains": ["## Completed", "## Carry-over", "## Verified by", "schema freeze"],
        },
        "timeout": 480,
    },
    "team-sprint-start": {
        "fixture": {
            "context.txt": (
                "Team context: platform team, capacity 20 points, one engineer on "
                "call. Committed backlog: the importer rollout (8 points), the "
                "weekend job fix (5 points), review-latency work (5 points).\n"
            ),
        },
        "prompt": _standard(
            "context.txt holds the team context and the committed backlog. Start "
            "the sprint with the installed skill. The artifact must have the sections "
            "'## Sprint goal', '## Committed scope', and '## Capacity check'; the "
            "committed scope must total at most 20 points and say which item stays "
            "out if capacity does not fit."
        ),
        "checks": {
            "contains": ["## Sprint goal", "## Committed scope", "## Capacity check", "20"],
        },
        "timeout": 480,
    },
    "verification": {
        "fixture": {
            "claim.txt": "The developer claims: 'the importer retry fix is complete and verified'.\n",
            "check.sh": "#!/bin/sh\nprintf 'verification: OK\\n'\n",
        },
        "prompt": (
            "You are running the acceptance fixture for the installed verification "
            "skill. claim.txt carries a completion claim; check.sh is the only "
            "available verification command. Apply the skill: run `sh check.sh` "
            "yourself, and gate the claim on its real output. The artifact must have "
            "the sections '## Claim', '## Command', and '## Observed output', and "
            "must quote the real output of the run.\n"
            "Write the artifact to {artifact}.\n"
            "Then write a JSON object with exactly three keys to {answer}:\n"
            "- artifact: the absolute path of the artifact file you wrote\n"
            "- command: the exact verification command you ran\n"
            '- status: exactly "passed" or "failed", per the observed output\n'
            "Rules: use only the installed skill as your method; do not access the "
            "network; do not modify any file other than the artifact; do not ask "
            "questions in chat; write every demanded section header exactly as "
            "spelled."
        ),
        "checks": {
            "answer_keys": ["artifact", "command", "status"],
            "answer_equal": {"status": "passed"},
            "contains": ["## Claim", "## Command", "## Observed output", "verification: OK"],
            "rerun": ["sh", "check.sh"],
        },
        "timeout": 480,
    },
}
