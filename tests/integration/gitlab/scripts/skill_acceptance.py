"""Optional live acceptance: one real agent completes the full code-review run.

The task builds the fake-glab fixture, isolates HOME/XDG like the eval host
adapters do, installs the built ``code-review`` archive, and asks one real
``opencode run --standalone`` session to drive the complete one-process review
cycle from a temporary checkout: poll, critic import, decision, prose edit,
runbook. Verification reads only machine artifacts and the stdout JSONL events
(read tool events, agent text), never the host session database.

Honest boundaries, also documented in ``docs/reviewmatic-test-matrix.md``:
the GitLab host is the fake-glab fixture rather than a real server, and
publication stays unexecuted. The critic is required to be an independent
subagent session (opencode's subagent tool provides one; the runtime rejects a
primary-session receipt), so the panel independence contract holds. The task
is explicitly optional (like ``eval:live``): it needs provider credentials and
never runs inside ``task check``, ``check:core``, Lefthook hooks, or CI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tests.integration.gitlab.scripts.stand import ROOT, load, private_directory, write_json

FAKE_GLAB_HELPERS = ROOT / "apps/reviewmatic/tests"
LIVE_CHECKS = ROOT / "tests/integration/mattermost/scripts/live_checks.py"

PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_CLI_CONFIG_CONTENT",
    "ZAI_API_KEY",
    "ZHIPU_API_KEY",
)

MR_URL = "https://gitlab.example/group/project/-/merge_requests/7"

# AC4 measures the full review cycle wall clock on this fixture; exceeding the
# budget is a red verdict, not a warning. The budget applies to this fixture
# composition (one-file MR, one linked issue, one model critic) and is recorded
# in the report next to the timings.
ACCEPTANCE_BUDGET_SECONDS = 1800.0
WATCH_INTERVAL = 3.0

# The default acceptance model must stay cheap; anything else is an explicit
# cost decision gated by ACCEPT_EXPENSIVE=1.
CHEAP_MODEL = re.compile(r"flash|mini|haiku|nano|lite", re.IGNORECASE)

# One linked issue seeds closes_issues so the live cycle collects it with its
# author_text origin, mirroring the deterministic layer's acceptance assert.
RELATED_ISSUE = {
    "iid": 5,
    "title": "Bound the retry writes behind an idempotency key",
    "state": "opened",
    "web_url": "https://gitlab.example/group/project/-/issues/5",
}

# Reference files a clean one-process run must never read: the local-WIP mode,
# the marked repair path, stages reached only outside this run, and the complete
# machine contracts the reading discipline forbids. Grounded in the stage router
# (references/workflow.md) of the built skill.
FORBIDDEN_REFERENCES = frozenset(
    {
        "local-review.md",
        "remote-review-stages.md",
        "review-state-machine.md",
        "repair.md",
        "publication.md",
        "incremental-review.md",
        "documentation-review.md",
        "portable-gitlab-contracts-v2.md",
        "portable-gitlab-contracts-v2.schema.json",
    }
)


class TransportError(RuntimeError):
    """The host failed to run; a retry is meaningful (timeout, provider error)."""


class VerificationError(RuntimeError):
    """A machine check failed; the acceptance is red and a retry cannot fix it."""


def settings() -> dict[str, Any]:
    # Defaults keep the task runnable with provider credentials alone; every
    # value stays overridable through its EVAL_* environment variable.
    os.environ.setdefault("EVAL_HOST", "opencode")
    os.environ.setdefault("EVAL_MODEL", "zai-coding-plan/glm-5.3-flash")
    os.environ.setdefault("EVAL_TIMEOUT", "5400")
    os.environ.setdefault("EVAL_MAX_TOKENS", "4000000")
    os.environ.setdefault("EVAL_MAX_COST", "40")
    configured = load("skills_acceptance_live_common", LIVE_CHECKS).settings()
    if not any(os.environ.get(key) for key in PROVIDER_KEYS):
        raise ValueError("Live acceptance requires explicit provider credentials/configuration")
    value = cast("dict[str, Any]", configured)
    if value["host"] != "opencode":
        # The verification reads opencode's stdout JSONL tool events, so the
        # acceptance is defined for the opencode host only.
        raise ValueError("Skill acceptance drives the opencode host only")
    model = str(value["model"])
    if not CHEAP_MODEL.search(model) and os.environ.get("ACCEPT_EXPENSIVE") != "1":
        raise ValueError(
            f"EVAL_MODEL={model} is not a known cheap (flash-class) model; "
            "export ACCEPT_EXPENSIVE=1 to accept the cost explicitly"
        )
    print(
        f"[acceptance] model: {model}"
        f" | timeout: {value['timeout_seconds']:.0f}s"
        f" | budget guardrails: <=${value['max_cost']:.2f}"
        f", <= {value['max_tokens']} tokens"
        f" | last measured cost: {last_measured_cost()}",
        flush=True,
    )
    return value


def last_measured_cost() -> str:
    """The previous run's measured cost, for the pre-flight estimate line."""
    pointer = ROOT / ".build/skill-acceptance/latest.json"
    try:
        report_path = Path(str(json.loads(pointer.read_text(encoding="utf-8"))["report"]))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        costs = [
            float(attempt["usage"]["cost"])
            for attempt in report.get("attempts", [])
            if isinstance(attempt.get("usage"), dict)
            and isinstance(attempt["usage"].get("cost"), (int, float))
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return "unknown (no prior run)"
    if not costs:
        return "unknown (no measured prior run)"
    return f"~${max(costs):.2f}"


def fake_glab() -> str:
    """The existing fake glab from the reviewmatic fixture: never a new stub."""
    module = load("skills_acceptance_fake_glab", FAKE_GLAB_HELPERS / "helpers/review_fixture.py")
    glab: Any = module.FAKE_GLAB
    return str(glab)


def pinned_runtime() -> str:
    # The acceptance validates the current working tree (decision 51: the user
    # commits only after a green acceptance), so the pin prefers a dangling
    # working-tree commit created by `git stash create` — no ref or index
    # movement — and falls back to HEAD on a clean tree.
    staged = subprocess.run(
        ["git", "-C", str(ROOT), "stash", "create"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not staged:
        staged = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    return f"git+file://{ROOT}/.git@{staged}#subdirectory=apps/reviewmatic"


def git(*arguments: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def build_fixture(directory: Path, overrides: dict[str, Any]) -> tuple[Path, Path]:
    """The review-fixture repository: checkout, bare origin, and one fake glab."""
    for name in ("bin", "checkout"):
        (directory / name).mkdir(parents=True)
    bin_dir = directory / "bin"
    (bin_dir / "glab").write_text(fake_glab())
    (bin_dir / "glab").chmod(0o755)
    repo = directory / "checkout"
    git("init", "--quiet", "--initial-branch=main", cwd=repo)
    git("config", "commit.gpgsign", "false", cwd=repo)
    git("config", "user.email", "reviewer@example.invalid", cwd=repo)
    git("config", "user.name", "Example Reviewer", cwd=repo)
    (repo / "review.txt").write_text("base\n")
    (repo / "index.txt").write_text("imports review.txt\n")
    git("add", "review.txt", "index.txt", cwd=repo)
    git("commit", "-qm", "base", cwd=repo)
    base = git("rev-parse", "HEAD", cwd=repo)
    (repo / "review.txt").write_text("base\nreviewed change\n")
    git("commit", "-qam", "change", cwd=repo)
    head = git("rev-parse", "HEAD", cwd=repo)
    origin = directory / "origin.git"
    git("init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    git("remote", "add", "origin", "https://gitlab.example/group/project.git", cwd=repo)
    git("config", f"url.{origin}.insteadOf", "https://gitlab.example/group/project.git", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    git("branch", "dev", head, cwd=repo)
    git("push", "-q", "origin", "dev", cwd=repo)
    git("-C", str(origin), "update-ref", "refs/merge-requests/7/head", head)
    config = {
        "baseSha": base,
        "startSha": base,
        "headSha": head,
        "changedPath": "review.txt",
        "requests": str(directory / "requests.log"),
        **overrides,
    }
    (directory / "glab-config.json").write_text(json.dumps(config))
    (directory / "requests.log").write_text("")
    return repo, bin_dir


def agent_catalog(directory: Path, workspace: Path, model: str) -> None:
    """Pre-seed the host agent inventory the poll grounding rules read."""
    definition = (
        "---\n"
        "description: Acceptance reviewer available on this host\n"
        f"model: {model}\n"
        "---\n"
        "One model agent in the acceptance inventory. The single entry keeps the\n"
        "independence rule satisfiable: multi-critic compositions require distinct\n"
        "models or engines, and two critics on one model are not independent.\n"
    )
    for config_home in (
        directory / "home" / ".config" / "opencode" / "agents",
        directory / "xdg-config" / "opencode" / "agents",
        workspace / ".opencode" / "agents",
    ):
        config_home.mkdir(parents=True, exist_ok=True)
        (config_home / "acceptance-reviewer.md").write_text(definition)


def build_environment(directory: Path, bin_dir: Path, configured: dict[str, Any]) -> dict[str, str]:
    adapter = load("skills_acceptance_adapter", ROOT / "scripts/eval_runner.py")
    raw = adapter.isolated_environment(directory)
    assert isinstance(raw, dict)
    environment = {str(key): str(value) for key, value in raw.items()}
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "FAKE_GLAB_CONFIG": str(directory / "glab-config.json"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_COLOR": "1",
            "REVIEWMATIC_FROM": pinned_runtime(),
        }
    )
    cache = os.environ.get("UV_CACHE_DIR")
    if not cache and (Path.home() / ".cache" / "uv").is_dir():
        cache = str(Path.home() / ".cache" / "uv")
    if cache:
        # Keep the uvx build warm across attempts without sharing anything else.
        environment["UV_CACHE_DIR"] = cache
    for key in PROVIDER_KEYS:
        if key in os.environ:
            environment[key] = os.environ[key]
    assert isinstance(configured["model"], str)
    return environment


def build_workspace(directory: Path, configured: dict[str, Any]) -> Path:
    workspace = private_directory(directory / "workspace")
    built = ROOT / ".build/skills/code-review"
    if not (built / "SKILL.md").is_file():
        raise ValueError("The built code-review archive is missing; run task skills:build")
    shutil.copytree(built, workspace / ".agents/skills/code-review")
    agent_catalog(directory, workspace, str(configured["model"]))
    return workspace


def prompt(workspace: Path, repo: Path, answer: Path) -> str:
    return (
        "Run the installed code-review skill end to end for this exact merge request: "
        f"{MR_URL}\n"
        f"The reviewed checkout is {repo}. Use the skill's one-process run path "
        "(`reviewmatic run`) with review mode normal and the en locale.\n"
        "\n"
        "Environment facts, prepared for you:\n"
        "- The glab CLI on PATH talks to an isolated fixture GitLab and is the only "
        "reachable host. Treat it as the real GitLab.\n"
        "- REVIEWMATIC_FROM is pre-pinned in your environment to the local "
        "pre-publication revision. Use it for every reviewmatic invocation exactly as "
        "the skill instructs, and verify the pin with `reviewmatic runtime-info`.\n"
        "- I am the user. When the run stops at the panel poll, present the poll text "
        "verbatim: echo the exact printed characters as plain text, same lines, no "
        "blockquote markers, no rewrapping, nothing added between the lines. Then ask me "
        "the composition question with your native interactive question tool, offering at "
        "least the recommended composition, a single model subagent, a subagent plus an "
        "OCR critic, and a custom composition; this run is non-interactive, so the "
        "question tool will be cancelled — my pre-given answer then stands: critics: one "
        'model critic named critic-1 with engine "model"; arbitrator: arbitrator-1. '
        "Fill the selection template from that answer yourself and run the printed "
        "command yourself; do not ask me to write JSON.\n"
        "- A recorded refusal names the rule, the offending path, the valid form, and "
        "when needed the exact repair command: correct the offending authored artifact "
        "and run that printed command (it rebinds the artifact and rewinds the derived "
        "stages). Never edit a bound artifact file behind the runtime's back, never "
        "re-derive a refusal from contract references, and never execute publication "
        "mutations to force a stage.\n"
        "- Exactly one authoring step is delegated: the critic receipt. Launch the critic as "
        "an independent subagent session over the collected context (your subagent tool "
        "provides real independent sessions), have it fill the receipt verbatim with its "
        "genuine findings, and import it with the printed record-run-critic command. The "
        "receipt keeps the printed run_id exactly as emitted, and its session_id is the "
        "SUBAGENT's own real session id taken from the subagent's own session metadata — "
        "never your session id, never an invented string.\n"
        "- The review decision is the opposite: you author it yourself, in this primary "
        "session, never through a subagent. Fill the decision template's run_id with the "
        "exact string primary-review and session_id with your own real session id from your "
        "session metadata. Both identities must differ from every run_id and session_id in "
        "the critic receipt: the runtime rejects a decision that reuses the critic's "
        "identity as non-independent.\n"
        "- Author the generated prose file yourself too: when the run stops for prose it "
        "prints the prose file path and the exact record-prose command — edit that file "
        "yourself, run the printed record-prose command, then run --resume. Never run "
        "template-review, scaffold-review, or check-review: those are repair interfaces, "
        "not the one-process run path. Then keep driving the cycle: run "
        "every printed continuation command through the pinned runtime until the review "
        "reaches its final plan. Never leave the one-process run path: at every stop, run "
        "exactly the next_action command the runtime just printed (run --resume, "
        "record-run-critic, finalize-review, or record-prose); do "
        "not restart the review, do not switch to other review interfaces, and do not "
        "re-derive stops through repair paths. Only the code-review skill "
        "is installed; do not require others.\n"
        "- Never execute publication commands; the review ends at the runbook. Keep the review "
        "state in the XDG state directory your environment already provides: never create "
        "additional state trees and never move or rename existing ones.\n"
        "\n"
        "When the review reaches its final plan, write a JSON object with exactly two "
        f"keys to {answer}:\n"
        "- artifact_root: the reviewmatic artifact root (absolute path)\n"
        "- runbook: the final runbook Markdown path (absolute path)\n"
        "Write that answer immediately from the paths the run already printed; do not "
        "read any further reference or documentation files after the final plan — the "
        "run's own outputs are sufficient, and out-of-stage reference reads violate the "
        "skill's reading discipline.\n"
    )


def scrub(text: str, adapter: Any) -> str:
    for key in PROVIDER_KEYS:
        if os.environ.get(key):
            text = text.replace(os.environ[key], "[REDACTED]")
    return str(adapter.redact_text(text))


def spawn(
    argv: list[str],
    workspace: Path,
    environment: dict[str, str],
    timeout: float,
    label: str = "acceptance",
) -> tuple[str, str, int]:
    started = time.monotonic()
    with subprocess.Popen(
        argv,
        cwd=workspace,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        quiet = threading.Event()

        def beat() -> None:
            while not quiet.wait(60):
                elapsed = int(time.monotonic() - started)
                print(
                    f"[{label}] agent still running: {elapsed}s elapsed (pid {process.pid})",
                    flush=True,
                )

        watchdog = threading.Thread(target=beat, daemon=True)
        watchdog.start()
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            raise TransportError("live host exceeded its timeout") from None
        finally:
            quiet.set()
    print(f"[{label}] agent finished in {int(time.monotonic() - started)}s", flush=True)
    return stdout, stderr, process.returncode


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def watch_stages(directory: Path, stop: threading.Event, stages: dict[str, int]) -> None:
    """Record the wall-clock second each run-path stage first becomes observable.

    The watcher only reads the isolated acceptance state tree while the agent
    runs; the review cycle writes its stage artifacts there, so first sighting
    of each artifact is the honest stage boundary for the AC4 timeline.
    """
    started = time.monotonic()

    def mark(name: str) -> None:
        stages.setdefault(name, round(time.monotonic() - started))

    state = directory / "xdg-state"
    while not stop.wait(WATCH_INTERVAL):
        if not state.is_dir():
            continue
        for progress_path in state.rglob("review-current.json"):
            mark("prepare")
            progress = read_json_file(progress_path)
            if not progress:
                continue
            if progress.get("context_path"):
                mark("context")
            if progress.get("critic_receipt_path"):
                mark("arbitration")
            if progress.get("finalize_report_path"):
                mark("finalize-report")
            if progress.get("decision_path"):
                mark("decision")
            if progress.get("plan_path"):
                mark("finalize")
        for panel_path in state.rglob("review-panel.json"):
            panel = read_json_file(panel_path)
            if not panel:
                continue
            participants = panel.get("participants")
            if not isinstance(participants, dict):
                continue
            mark("poll-panel")
            critics = participants.get("critics") or []
            if any(
                isinstance(critic, dict) and isinstance(critic.get("receipt"), dict)
                for critic in critics
            ):
                mark("critic")
        for authoring_path in state.rglob("run-authoring.json"):
            authoring = read_json_file(authoring_path)
            if authoring and authoring.get("applied") is True:
                mark("prose")


def stage_timeline(stages: dict[str, int]) -> list[dict[str, Any]]:
    """Ordered AC4 timeline with the gaps between observed stage boundaries."""
    order = (
        ("prepare", "prepare: run started, evidence snapshotted"),
        ("context", "context: review context collected"),
        ("poll-panel", "poll-panel: panel poll answered and recorded"),
        ("critic", "critic: independent critic receipt imported"),
        ("arbitration", "arbitration: panel completed and its receipt bound"),
        ("finalize-report", "finalize-report: finalize report bound"),
        ("decision", "decision: review decision recorded"),
        ("prose", "prose: generated prose authored"),
        ("finalize", "finalize: final runbook plan reached"),
    )
    timeline: list[dict[str, Any]] = []
    previous = 0
    for name, description in order:
        at = stages.get(name)
        if at is None:
            timeline.append({"stage": name, "at_seconds": None, "gap_seconds": None})
            continue
        timeline.append(
            {
                "stage": name,
                "at_seconds": at,
                "gap_seconds": at - previous,
                "description": description,
            }
        )
        previous = at
    return timeline


def write_summary(path: Path, report: dict[str, Any]) -> None:
    """The human-readable twin of result.json (AC2: every run leaves one)."""
    lines = [
        "# Skill acceptance report",
        "",
        f"- action: `{report.get('action')}`",
        f"- started at: {report.get('started_at')}",
        f"- verdict: **{report.get('status')}**",
    ]
    fixture = report.get("fixture")
    if isinstance(fixture, dict):
        lines += [
            "",
            "## Fixture composition (the 30-minute budget is valid for exactly this)",
            "",
            f"- merge request: {fixture.get('mr_url')}",
            f"- changed path: `{fixture.get('changed_path')}`",
            f"- linked issue: iid {fixture.get('related_issue_iid')}",
            "- host: fake-glab fixture (no real GitLab server), publication unexecuted",
        ]
    lines += [
        "",
        "| attempt | status | model | wall clock | within 30 min |",
        "| --- | --- | --- | --- | --- |",
    ]
    for attempt in report.get("attempts", []):
        wall = attempt.get("duration_ms")
        wall_text = f"{wall / 1000:.0f}s" if isinstance(wall, (int, float)) else "n/a"
        within = attempt.get("within_budget")
        lines.append(
            f"| {attempt.get('attempt')} | {attempt.get('status')} | {attempt.get('model', 'n/a')} "
            f"| {wall_text} | {'yes' if within else 'no'} |"
        )
    for attempt in report.get("attempts", []):
        if attempt.get("status") != "passed":
            if attempt.get("error"):
                lines += ["", f"## Attempt {attempt.get('attempt')}: failure", "", attempt["error"]]
            continue
        lines += ["", f"## Attempt {attempt.get('attempt')} timeline", ""]
        timeline = attempt.get("timeline") or []
        if timeline:
            lines += ["| stage | at (s) | gap (s) |", "| --- | --- | --- |"]
            for item in timeline:
                at = item.get("at_seconds")
                gap = item.get("gap_seconds")
                lines.append(
                    f"| {item.get('stage')} | {at if at is not None else '-'} "
                    f"| {gap if gap is not None else '-'} |"
                )
        checks = attempt.get("checks") or []
        if checks:
            lines += ["", "| check | status |", "| --- | --- |"]
            lines += [f"| {item.get('name')} | {item.get('status')} |" for item in checks]
        usage = attempt.get("usage")
        if isinstance(usage, dict):
            cost = usage.get("cost")
            cost_text = f"${cost}" if cost is not None else "?"
            lines += [
                "",
                f"Usage: {usage.get('total_tokens', '?')} tokens, {cost_text}",
            ]
    lines += [
        "",
        "## Machine report",
        "",
        "Verifiable evidence lives in `result.json` next to this file.",
        "",
        "## Handing this report to the master session",
        "",
        (
            "Paste the verdict line, the attempt table, the failed-attempt errors, and the "
            "`result.json` path into the master session; the raw per-attempt outputs stay "
            "under the private report directory referenced by `result.json`."
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    malformed = ""
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Cosmetic host noise (spinner control sequences and the like) must
            # not consume an attempt; only an eventless stream is a failure.
            malformed = malformed or line[:200]
            continue
        if isinstance(event, dict):
            events.append(event)
    if not events:
        raise TransportError(f"live host emitted no structured events; first noise: {malformed}")
    return events


def tool_paths(events: list[dict[str, Any]], names: set[str]) -> list[str]:
    paths: list[str] = []
    for event in events:
        if event.get("type") != "tool_use":
            continue
        part = cast("dict[str, Any]", event.get("part") or {})
        if part.get("tool") not in names:
            continue
        state = cast("dict[str, Any]", part.get("state") or {})
        argument = cast("dict[str, Any]", state.get("input") or {})
        path = argument.get("path")
        if isinstance(path, str):
            paths.append(path)
    return paths


def agent_text(events: list[dict[str, Any]]) -> str:
    return "\n".join(
        str(cast("dict[str, Any]", event.get("part") or {}).get("text") or "")
        for event in events
        if event.get("type") == "text"
    )


def expected_poll_text(progress: dict[str, Any]) -> str:
    from reviewmatic import run_panel

    locale = str(progress.get("locale") or "en")
    mode = str(progress.get("mode") or "normal")
    if locale not in {"en", "ru"} or mode != "normal":
        raise VerificationError(f"unexpected review locale/mode: {locale}/{mode}")
    # The tiny fixture never exceeds the OCR background limit, so the poll note
    # is empty and the presented text is the canonical locale text verbatim.
    return str(run_panel.poll(locale, mode, 0)["text"])


def load_json(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"{label} is not a JSON object")
    return value


def verify(
    attempt: dict[str, Any], directory: Path, workspace: Path, stdout: str
) -> dict[str, Any]:
    """Machine verification over artifacts and stdout events; raises when red."""
    adapter = load("skills_acceptance_adapter", ROOT / "scripts/eval_runner.py")
    environment = attempt["environment"]
    events = parse_events(stdout)
    usage = load("skills_acceptance_usage", LIVE_CHECKS).usage(events, adapter)

    answer_path = workspace / "answer.json"
    if not answer_path.is_file():
        raise VerificationError("the agent did not write answer.json")
    answer = load_json(answer_path, "answer")
    if set(answer) != {"artifact_root", "runbook"}:
        raise VerificationError(f"answer.json keys are {sorted(answer)}")
    artifact_root = Path(str(answer["artifact_root"])).resolve()
    if not artifact_root.is_relative_to(directory) or not artifact_root.is_dir():
        raise VerificationError("artifact_root is outside the isolated acceptance state")
    runbook = Path(str(answer["runbook"])).resolve()
    if runbook != artifact_root / "runbook.md" or not runbook.is_file():
        raise VerificationError("the reported runbook is not the artifact runbook")

    progress = load_json(artifact_root / "review-current.json", "review progress")
    if progress.get("stage") != "plan_ready":
        raise VerificationError(f"the review stopped at stage {progress.get('stage')!r}")

    # The critic import really happened: the panel binds the recorded receipt.
    panel = load_json(artifact_root / "review-panel.json", "run panel")
    critics = cast("list[dict[str, Any]]", panel.get("participants", {}).get("critics") or [])
    receipts = cast("list[dict[str, Any]]", panel.get("receipts") or [])
    if not (
        len(critics) == 1
        and critics[0].get("name") == "critic-1"
        and isinstance(critics[0].get("receipt"), dict)
        and len(receipts) == 1
    ):
        raise VerificationError("the panel has no bound critic-1 receipt")

    # The prose tail really was authored: the agent's edited prose is recorded.
    authoring = load_json(artifact_root / "run-authoring.json", "run authoring")
    if not authoring.get("prose_input") or authoring.get("applied") is not True:
        raise VerificationError("no authored prose input was recorded")

    # The poll was presented verbatim, per the poll rules contract.
    presented = agent_text(events)
    if expected_poll_text(progress) not in presented:
        raise VerificationError("the agent did not present the poll text verbatim")

    # Decision 71: the composition choice is collected through the host's
    # native interactive question tool with the minimum option set. In this
    # non-interactive run the tool use is cancelled (state status error) — the
    # use itself, its option set, and the imported selection are what counts.
    question_uses = [
        cast("dict[str, Any]", event.get("part") or {})
        for event in events
        if event.get("type") == "tool_use"
        and cast("dict[str, Any]", event.get("part") or {}).get("tool") == "question"
    ]
    if not question_uses:
        raise VerificationError("the agent did not ask the composition question interactively")
    option_text = " ".join(
        json.dumps(cast("dict[str, Any]", use.get("state") or {}).get("input") or {})
        for use in question_uses
    ).lower()
    for option in ("recommended", "model subagent", "ocr", "custom"):
        if option not in option_text:
            raise VerificationError(f"the composition question is missing the {option!r} option")

    # Reading discipline: zero reads of out-of-stage reference files.
    skill_root = str(workspace / ".agents/skills/code-review")
    forbidden = []
    reference_reads = []
    for path in tool_paths(events, {"read"}):
        if not path.startswith(skill_root + "/references/"):
            continue
        reference_reads.append(path)
        if Path(path).name in FORBIDDEN_REFERENCES:
            forbidden.append(path)
    if forbidden:
        raise VerificationError(f"out-of-stage reference reads: {sorted(forbidden)}")

    # The publication boundary held: the fake glab recorded no mutations.
    config = load_json(directory / "glab-config.json", "fixture config")
    if config.get("publishedNotes") or "resolved" in config:
        raise VerificationError("the agent executed a publication mutation")

    # Independent revalidation of the whole artifact chain against the fixture.
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            environment["REVIEWMATIC_FROM"],
            "reviewmatic",
            "report-review",
            "--artifact-root",
            str(artifact_root),
            "--json",
        ],
        env=environment,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    report = json.loads(completed.stdout) if completed.returncode == 0 else {}
    if report.get("status") != "ok":
        raise VerificationError(
            f"report-review revalidation failed: {completed.stdout[-400:] or completed.stderr[-400:]}"
        )

    budgets, budget_status = adapter.budget_assertions(usage, dict(attempt["configured"]))
    if budget_status == "blocked":
        raise VerificationError("live budget evidence is blocked")
    return {
        "status": "passed",
        "artifact_root": str(artifact_root),
        "runbook": str(runbook),
        "checks": [
            {"name": "plan_ready", "status": "passed"},
            {"name": "critic-import", "status": "passed"},
            {"name": "prose-authored", "status": "passed"},
            {"name": "poll-verbatim", "status": "passed"},
            {"name": "poll-question", "status": "passed", "uses": len(question_uses)},
            {"name": "reference-discipline", "status": "passed", "reads": len(reference_reads)},
            {"name": "no-publication-mutation", "status": "passed"},
            {"name": "report-review", "status": "passed"},
        ],
        "reference_reads": sorted(reference_reads),
        "usage": usage,
        "budgets": budgets,
    }


def run_attempt(directory: Path, configured: dict[str, Any], adapter: Any) -> dict[str, Any]:
    repo, bin_dir = build_fixture(directory, {"closesIssues": [RELATED_ISSUE]})
    environment = build_environment(directory, bin_dir, configured)
    workspace = build_workspace(directory, configured)
    answer = workspace / "answer.json"
    argv = cast(
        "list[str]",
        adapter.host_command(
            "opencode", "opencode", str(configured["model"]), prompt(workspace, repo, answer)
        ),
    )
    # --standalone belongs to the `run` subcommand on opencode v2.
    argv.insert(2, "--standalone")
    stop = threading.Event()
    stages: dict[str, int] = {}
    watcher = threading.Thread(target=watch_stages, args=(directory, stop, stages), daemon=True)
    watcher.start()
    started = time.monotonic()
    try:
        stdout, stderr, code = spawn(
            argv, workspace, environment, float(configured["timeout_seconds"])
        )
    finally:
        stop.set()
        watcher.join()
    (directory / "agent-output.txt").write_text(scrub(stdout + "\n" + stderr, adapter))
    if code != 0:
        raise TransportError(f"live host exited {code}")
    attempt: dict[str, Any] = {
        "environment": environment,
        "configured": {
            "max_tokens": configured["max_tokens"],
            "max_cost": configured["max_cost"],
        },
    }
    try:
        result = verify(attempt, directory, workspace, stdout)
    except VerificationError as error:
        verification_evidence(error, directory, stages, started)
        raise
    duration_ms = round((time.monotonic() - started) * 1000)
    result["duration_ms"] = duration_ms
    result["model"] = str(configured["model"])
    result["timeline"] = stage_timeline(stages)
    result["within_budget"] = duration_ms <= ACCEPTANCE_BUDGET_SECONDS * 1000
    if not result["within_budget"]:
        raise VerificationError(
            f"the review cycle took {duration_ms / 1000:.0f}s, over the "
            f"{ACCEPTANCE_BUDGET_SECONDS:.0f}s acceptance budget (AC4 red verdict)"
        )
    return result


def verification_evidence(
    error: VerificationError,
    directory: Path,
    stages: dict[str, int],
    started: float,
) -> None:
    """Leave the AC4 timeline behind even when verification fails red."""
    payload = {
        "error": str(error),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "timeline": stage_timeline(stages),
        "within_budget": round((time.monotonic() - started) * 1000)
        <= ACCEPTANCE_BUDGET_SECONDS * 1000,
    }
    (directory / "verification-failure.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=2)
    arguments = parser.parse_args()
    if arguments.attempts < 1:
        parser.error("--attempts must be positive")
    configured = settings()
    adapter = load("skills_acceptance_adapter", ROOT / "scripts/eval_runner.py")
    root = private_directory(
        ROOT
        / ".build/skill-acceptance"
        / (time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3))
    )
    report: dict[str, Any] = {
        "action": "skill-acceptance",
        "started_at": datetime.now(UTC).isoformat(),
        "attempts": [],
        "status": "failed",
        "acceptance_budget_seconds": ACCEPTANCE_BUDGET_SECONDS,
        "fixture": {
            "mr_url": MR_URL,
            "changed_path": "review.txt",
            "related_issue_iid": RELATED_ISSUE["iid"],
            "host": "fake-glab fixture; publication unexecuted",
        },
    }
    verdict: dict[str, Any] | None = None
    try:
        for index in range(1, arguments.attempts + 1):
            attempt_dir = private_directory(root / f"attempt-{index}")
            try:
                verdict = run_attempt(attempt_dir, configured, adapter)
            except TransportError as error:
                report["attempts"].append(
                    {
                        "attempt": index,
                        "status": "retryable",
                        "error": str(error),
                        "output": str(attempt_dir / "agent-output.txt"),
                    }
                )
                if index < arguments.attempts:
                    # Provider outages and rate limits are transient; wait
                    # before the next attempt instead of retrying into the
                    # same blip.
                    time.sleep(60)
                continue
            except VerificationError as error:
                report["attempts"].append(
                    {
                        "attempt": index,
                        "status": "failed",
                        "error": str(error),
                        "output": str(attempt_dir / "agent-output.txt"),
                    }
                )
                break
            verdict["attempt"] = index
            report["attempts"].append(verdict)
            break
    finally:
        report["status"] = "passed" if verdict is not None else "failed"
        write_json(root / "result.json", report)
        write_json(
            root.parent / "latest.json",
            {"report": str(root / "result.json"), "status": report["status"]},
        )
        write_summary(root / "summary.md", report)
        print("Report: " + str(root / "result.json"))
        print("Summary: " + str(root / "summary.md"))
    return 0 if verdict is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
