"""Deterministic end-to-end checks against an initialized local test stand."""

from __future__ import annotations

import contextlib
import copy
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from stand import load, private_directory, write_json

ROOT = Path(__file__).resolve().parents[3]


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def card_checks(
    stand: Any,
    report_dir: Path,
    scripts: Path,
    cli: Any,
    publication: Any,
    environment: dict[str, str],
) -> dict[str, Any]:
    reader = scripts / "mattermost.py"
    guide = (scripts.parent / "references/cards.md").read_text()
    examples = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", guide, re.S)]
    for locale, sentence in (
        ("en", "Check concurrent retries. "),
        ("ru", "Проверяем повторную отправку. "),
    ):
        near = copy.deepcopy(
            next(c for c in examples if c["kind"] == "mr" and c["locale"] == locale)
        )
        near["title"] = ("api!999 · Boundary fixture with a long descriptive title " * 2)[:100]
        near["summary"] = (sentence * 12)[:240]
        examples.append(near)
    bad = {**examples[0], "summary": "x" * 241}
    cli(
        reader,
        "publication",
        "prepare",
        data={
            "messages": [{"target": stand.url("cards"), "message": "", "files": [], "card": bad}]
        },
        expected=2,
    )
    browser_module = load("mm_stand_browser", Path(__file__).with_name("browser_checks.py"))
    browser = browser_module.Browser(stand, report_dir)
    results = []
    try:
        browser.start()
        environment.update(
            AGENT_BROWSER_SESSION=browser.session,
            AGENT_BROWSER_CONFIG=str(stand.state / "browser-config.json"),
        )
        preview = cli(reader, "auth", "preview", stand.origin)
        cli(
            reader,
            "auth",
            "apply",
            stand.origin,
            "--confirm",
            preview["digest"],
            "--browser-consent",
        )
        for index, card in enumerate(examples):
            post_id = publication(card=card)
            results += browser.check(
                post_id, card["title"], f"card-{index}-{card['locale']}", card["summary"]
            )
        negative = stand.request(
            "POST",
            "/posts",
            {
                "channel_id": stand.manifest["channels"]["cards"],
                "message": "",
                "props": {
                    "attachments": [
                        {"title": "Oversized control", "text": "Long paragraph. " * 300}
                    ]
                },
            },
            "reader",
        )
        try:
            browser.check(negative["id"], "Oversized control", "oversized-control")
        except RuntimeError as exc:
            require(
                "collapsed or overflowing" in str(exc),
                "Negative layout control failed for an unrelated reason",
            )
        else:
            raise RuntimeError("Browser detector missed the oversized control")
    except Exception:
        with contextlib.suppress(Exception):
            browser.call("screenshot", str(report_dir / "browser-failure.png"))
            (report_dir / "browser-failure.txt").write_text(browser.call("snapshot", "-i"))
        raise
    finally:
        environment.pop("AGENT_BROWSER_SESSION", None)
        environment.pop("AGENT_BROWSER_CONFIG", None)
        browser.close()
    return {
        "layouts": results,
        "invalid_card_rejected": True,
        "browser_auth": True,
        "negative_layout_control": True,
    }


def run(stand: Any, *, live: bool = False) -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    report_dir = private_directory(stand.reports / run_id)
    report: dict[str, Any] = {
        "status": "running",
        "project": stand.project,
        "origin": stand.origin,
        "mode": "live" if live else "deterministic",
        "checks": [],
    }

    def record(name: str, callback: Any) -> None:
        start = time.monotonic()
        try:
            evidence = callback()
            report["checks"].append({"name": name, "status": "passed", "evidence": evidence})
        except Exception as exc:
            report["checks"].append(
                {"name": name, "status": "failed", "error": stand.redact(str(exc))}
            )
        report["checks"][-1]["duration_ms"] = round((time.monotonic() - start) * 1000)
        write_json(report_dir / "result.json", report)

    def contracts() -> dict[str, Any]:
        result = subprocess.run(
            [  # noqa: S607 - Pinned Mise toolchain.
                "mise",
                "exec",
                "--",
                "uv",
                "run",
                "--locked",
                "pytest",
                "skills/mattermost/tests",
                "skills/mattermost-triage/tests",
                "tests/test_mattermost_stand.py",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        (report_dir / "contracts.log").write_text(stand.redact(result.stdout + result.stderr))
        require(result.returncode == 0, "Contract suite failed; see contracts.log")
        return {"exit_code": result.returncode, "log": "contracts.log"}

    record("contracts.regression-and-controlled-faults", contracts)

    scripts = ROOT / ".build/skills/mattermost/scripts"
    triage_scripts = ROOT / ".build/skills/mattermost-triage/scripts"
    mm = load("mm_stand_reader", scripts / "mattermost.py")
    pub = load("mm_stand_publication", scripts / "mattermost_publication.py")
    environment = stand.skill_environment()
    before_free = stand.request(
        "GET", f"/channels/{stand.manifest['channels']['free']}/posts?per_page=200", actor="reader"
    )
    with mock.patch.dict(os.environ, environment):
        mm.save_token(stand.origin, stand.manifest["users"]["reader"]["token"])

        def cli(script: Path, *args: str, data: object = None, expected: int = 0) -> dict[str, Any]:
            process = subprocess.run(  # noqa: S603 - Bundled skill scripts and fixture arguments.
                [sys.executable, "-I", "-S", "-B", str(script), *args],
                input=json.dumps(data) if data is not None else None,
                capture_output=True,
                text=True,
                env=environment,
                timeout=120,
                check=False,
            )
            try:
                result = json.loads(process.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{script.name} emitted no JSON: {process.stderr[-2000:]}"
                ) from exc
            require(
                process.returncode == expected,
                f"{script.name}: expected exit {expected}, got {process.returncode}: {result.get('errors', result.get('error', result.get('status')))}",
            )
            return result

        reader = scripts / "mattermost.py"
        until = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
        bounds = ("--since", "2000-01-01T00:00:00+00:00", "--until", until)

        def reads() -> dict[str, Any]:
            result = cli(reader, "read", stand.url("read"), *bounds, "--refresh")
            ids = {post["id"] for post in result["posts"]}
            require(
                result["complete"] and result["pages"]["posts"] >= 2,
                "Pagination did not cover multiple pages",
            )
            require(
                all(stand.manifest["posts"][f"page-{i:03d}"] in ids for i in range(205)),
                "Missing pagination fixtures",
            )
            cached = cli(reader, "read", stand.url("read"), *bounds)
            require(cached["cache_hit"], "Second read did not use cache")
            windows = cli(
                reader, "read", stand.url("read"), *bounds, "--view", "transcript", "--limit", "2"
            )
            require(
                windows["window"]["next_offset"] is not None,
                "Transcript did not expose continuation",
            )
            return {"posts": len(ids), "pages": result["pages"], "cache_hit": cached["cache_hit"]}

        record("read.pagination-cache-transcript", reads)

        def conversations() -> dict[str, Any]:
            results = {}
            for channel in ("direct", "group"):
                value = cli(reader, "read", stand.url(channel), *bounds)
                require(value["complete"] and value["posts"], f"Empty {channel}")
                results[channel] = value["counts"]
            root = stand.manifest["posts"]["thread-root"]
            url = f"{stand.origin}/{stand.manifest['team']['name']}/pl/{root}"
            result = cli(reader, "read", url, "--refresh")
            require(
                {root, stand.manifest["posts"]["thread-reply"]}
                <= {p["id"] for p in result["posts"]},
                "Thread incomplete",
            )
            require(any(p.get("reactions") for p in result["posts"]), "Reactions missing")
            omitted = cli(reader, "read", url, "--no-reactions")
            require(
                all(not p.get("reactions") for p in omitted["posts"]), "Reaction omission failed"
            )
            members = cli(reader, "members", stand.url("read"))
            require(members["complete"], "Membership incomplete")
            empty = cli(
                reader,
                "read",
                stand.url("read"),
                "--since",
                "2000-01-01T00:00:00Z",
                "--until",
                "2000-01-02T00:00:00Z",
            )
            require(empty["complete"] and not empty["posts"], "Period bounds ignored")
            return results

        record("read.threads-chats-reactions-members-period", conversations)

        def access() -> dict[str, Any]:
            denied = cli(reader, "read", stand.url("private"), expected=2)
            return {"status": denied["status"]}

        record("read.private-channel-denied", access)

        def cache_and_auth() -> dict[str, Any]:
            original = environment["XDG_CACHE_HOME"]
            environment["XDG_CACHE_HOME"] = str(private_directory(stand.state / "cache-clear-case"))
            try:
                cli(reader, "read", stand.url("direct"), *bounds)
                status = cli(reader, "cache", "status")
                require(status["counts"]["posts"] > 0, "Cache was not populated")
                preview = cli(reader, "cache", "clear")
                cli(reader, "cache", "clear", "--confirm", preview["digest"])
                require(
                    not cli(reader, "cache", "status")["exists"],
                    "Cache clear did not remove the owned cache",
                )
                cli(reader, "cache", "clear", "--confirm", preview["digest"], expected=2)
            finally:
                environment["XDG_CACHE_HOME"] = original
            original = environment["XDG_CONFIG_HOME"]
            environment["XDG_CONFIG_HOME"] = str(
                private_directory(stand.state / "unauthorized-case")
            )
            try:
                cli(reader, "read", stand.url("direct"), expected=3)
            finally:
                environment["XDG_CONFIG_HOME"] = original
            many = cli(
                reader, "read-many", stand.url("direct"), stand.url("private"), *bounds, expected=1
            )
            require(not many["complete"], "Mixed read-many result was incorrectly complete")
            return {
                "cache_clear": True,
                "replayed_receipt_rejected": True,
                "missing_auth": True,
                "partial_read_many": True,
            }

        record("cache.clear-auth-missing-partial-read-many", cache_and_auth)

        def publication(
            message: str = "", files: list[str] | None = None, card: object = None
        ) -> str:
            item: dict[str, Any] = {
                "target": stand.url("cards" if card else "publish"),
                "message": message,
                "files": files or [],
            }
            if card is not None:
                item["card"] = card
            plan = mm.prepare_publication({"messages": [item]})
            sealed = json.loads(
                (
                    Path(plan["plan_path"]).parent / "plans" / f"{plan['plan_digest']}.json"
                ).read_text()
            )
            entry = sealed["actions"][0]
            action, root, _ = pub.load_action(entry["path"], entry["digest"])
            outcome = pub.apply(action, root, entry["digest"])
            require(outcome[0] == "applied", f"Publication failed: {outcome}")
            require(
                pub.apply(action, root, entry["digest"])[0] == "already_applied",
                "Publication replay duplicated a post",
            )
            return outcome[3]["post_id"]

        def publications() -> dict[str, Any]:
            file = stand.state / "upload.txt"
            file.write_text("Owned upload fixture\n")
            file.chmod(0o600)
            post_id = publication("Automated publication fixture", [str(file)])
            remote = stand.request("GET", "/posts/" + post_id, actor="reader")
            require(len(remote["file_ids"]) == 1, "Upload missing")
            result = cli(
                reader, "read", f"{stand.origin}/{stand.manifest['team']['name']}/pl/{post_id}"
            )
            require("attachments" not in result["posts"][0], "Reader exposed excluded attachments")
            return {"post_id": post_id}

        record("publication.files-idempotency-reader-exclusion", publications)

        def recovery() -> dict[str, Any]:
            plan = mm.prepare_publication(
                {
                    "messages": [
                        {
                            "target": stand.url("publish"),
                            "message": "Lost response fixture",
                            "files": [],
                        }
                    ]
                }
            )
            entry = json.loads(
                (
                    Path(plan["plan_path"]).parent / "plans" / f"{plan['plan_digest']}.json"
                ).read_text()
            )["actions"][0]
            action, root, _ = pub.load_action(entry["path"], entry["digest"])
            original = pub.PublicationClient.create_post

            def lose_response(client: Any, payload: Any) -> Any:
                original(client, payload)
                raise pub.AmbiguousMutation("Injected lost response after real POST")

            with mock.patch.object(pub.PublicationClient, "create_post", lose_response):
                require(
                    pub.apply(action, root, entry["digest"])[0] == "blocked",
                    "Ambiguous POST not blocked",
                )
            found = pub.inspect(action, root, entry["digest"])
            require(found[0] == "applied" and found[3]["recovered"], "Lost response not recovered")
            return {"post_id": found[3]["post_id"], "fault": "lost response after real POST"}

        record("publication.ambiguous-post-recovery", recovery)

        def triage() -> dict[str, Any]:
            script = triage_scripts / "mattermost_triage.py"
            evidence = cli(
                script,
                "collect",
                "--origin",
                stand.origin,
                "--target",
                stand.url("read"),
                "--target",
                stand.url("direct"),
                *bounds,
            )
            require(evidence["complete"], "Triage collection incomplete")
            pid = stand.manifest["posts"]["direct-root"]
            raw = {
                "schema_version": 1,
                "evidence_digest": evidence["evidence_digest"],
                "summary": {"confidence": "high", "rationale": "Deterministic test fixture"},
                "candidates": [
                    {
                        "id": "retry-review",
                        "status": "attention",
                        "closure": "open",
                        "confidence": "high",
                        "rationale": "Explicit review request",
                        "source_post_ids": [pid],
                        "cited_excerpts": [
                            {"post_id": pid, "quote": "Please review the retry fix."}
                        ],
                        "draft_response": "I will review the retry fix.",
                        "response_target": stand.url("direct"),
                        "plan": None,
                    }
                ],
            }
            path = stand.state / "analysis-input.json"
            write_json(path, raw)
            published = cli(
                script, "publish", "--evidence", evidence["evidence_path"], "--analysis", str(path)
            )
            action = published["publication_commands"][0]
            result = cli(
                triage_scripts / "mattermost_triage_publication.py",
                "publish",
                "--action",
                action["path"],
                "--confirm",
                action["digest"],
            )
            require(result["status"] == "applied", "Triage publication failed")
            duplicate = cli(
                triage_scripts / "mattermost_triage_publication.py",
                "publish",
                "--action",
                action["path"],
                "--confirm",
                action["digest"],
            )
            require(
                duplicate["status"] == "already_applied", "Triage publication is not idempotent"
            )
            raw["candidates"][0]["cited_excerpts"][0]["quote"] = "Invented quotation"
            write_json(path, raw)
            cli(
                script,
                "publish",
                "--evidence",
                evidence["evidence_path"],
                "--analysis",
                str(path),
                expected=2,
            )
            later = cli(script, "collect", "--origin", stand.origin)
            require(
                later["period"]["since"] == evidence["period"]["until"],
                "Incremental watermark lost",
            )
            saved = json.loads(Path(later["evidence_path"]).read_text())
            require(
                any(p["selection"] == "carryover_unresolved" for p in saved["post_provenance"]),
                "Unresolved candidate not carried over",
            )
            return {
                "evidence_digest": evidence["evidence_digest"],
                "incremental": True,
                "carryover": True,
            }

        record("triage.collect-analysis-publication-incremental-carryover", triage)
        record(
            "cards.real-browser-both-locales-and-layouts",
            lambda: card_checks(stand, report_dir, scripts, cli, publication, environment),
        )

        def isolation() -> dict[str, Any]:
            after = stand.request(
                "GET",
                f"/channels/{stand.manifest['channels']['free']}/posts?per_page=200",
                actor="reader",
            )
            require(before_free == after, "Free-zone content changed")
            old = copy.deepcopy(stand.manifest)
            stand.bootstrap()
            require(old == stand.manifest, "Second initialization changed fixture identities")
            return {"free_zone_unchanged": True, "bootstrap_idempotent": True}

        record("stand.persistence-free-zone-idempotent-bootstrap", isolation)
        if live:
            live_module = load("mm_stand_live", Path(__file__).with_name("live_checks.py"))
            record("agent.live", lambda: live_module.run(stand, report_dir, environment))
    report["status"] = (
        "passed" if all(c["status"] == "passed" for c in report["checks"]) else "failed"
    )
    write_json(report_dir / "result.json", report)
    write_json(
        stand.reports / "latest.json",
        {"path": str(report_dir / "result.json"), "status": report["status"]},
    )
    print(json.dumps({"status": report["status"], "report": str(report_dir / "result.json")}))
    return 0 if report["status"] == "passed" else 1
