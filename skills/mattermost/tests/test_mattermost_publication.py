#!/usr/bin/env python3

import copy
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MM = load("mattermost_publication_prepare_test", SCRIPTS / "mattermost.py")
PUB = load("mattermost_publication_apply_test", SCRIPTS / "mattermost_publication.py")

CHANNEL_ID = "c" * 26
TEAM_ID = "t" * 26
USER_ID = "u" * 26
POST_ID = "p" * 26
ORIGIN = "https://chat.example.com"
TARGET = f"{ORIGIN}/team/channels/dev"


def sample_card(kind="issue", locale="en"):
    card = {
        "kind": kind,
        "template": "standard",
        "locale": locale,
        "title": "project#123 · Retry delivery",
        "url": "https://gitlab.example/project/-/issues/123",
        "summary": "Avoid duplicate notifications.",
        "status": "Open",
        "author": "Alice",
        "assignee": "Bob",
        "milestone": "1.2",
        "labels": ["bug"],
        "omitted_labels": 2,
    }
    if kind == "mr":
        card.update(pipeline="Passed", approvals="1/2")
    return card


class PrepareClient:
    def get(self, path):
        responses = {
            "/users/me": {"id": USER_ID},
            "/teams/name/team": {"id": TEAM_ID},
            f"/teams/{TEAM_ID}/channels/name/dev": {
                "id": CHANNEL_ID,
                "type": "O",
                "name": "dev",
                "team_id": TEAM_ID,
            },
        }
        return responses[path]


class ApplyClient(PrepareClient):
    def __init__(self, *, upload_error=False, create_error=False, recent=None):
        self.upload_error = upload_error
        self.create_error = create_error
        self.recent = recent
        self.uploads = []
        self.posts = []

    def upload(self, channel_id, name, data):
        self.uploads.append((channel_id, name, data))
        if self.upload_error:
            raise PUB.AmbiguousMutation("unknown")
        file_id = chr(ord("f") + len(self.uploads) - 1) * 26
        return {"file_infos": [{"id": file_id, "name": name}]}

    def create_post(self, payload):
        self.posts.append(payload)
        if self.create_error:
            raise PUB.AmbiguousMutation("unknown")
        return {"id": POST_ID, **payload}

    def get(self, path):
        if path == f"/posts/{POST_ID}":
            return {"id": POST_ID, **self.posts[-1]}
        if path.startswith(f"/channels/{CHANNEL_ID}/posts?"):
            posts = self.recent or []
            return {
                "order": [item["id"] for item in posts],
                "posts": {item["id"]: item for item in posts},
            }
        return super().get(path)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root / "state")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def prepare(self, messages):
        with (
            mock.patch.object(MM, "read_token", return_value="top-secret-token"),
            mock.patch.object(MM, "Client", return_value=PrepareClient()),
        ):
            result = MM.prepare_publication({"messages": messages})
        identity = MM.hashlib.sha256(f"{ORIGIN}\0{USER_ID}".encode()).hexdigest()
        root = self.root / "state" / "agent-skills" / "mattermost" / identity / "default"
        pointer = json.loads((root / "current-plan.json").read_text())
        plan = json.loads(Path(pointer["path"]).read_text())
        return result, root, plan

    def action(self, plan, index=0):
        entry = plan["actions"][index]
        return entry, json.loads(Path(entry["path"]).read_text())

    def test_prepare_creates_one_command_per_message_without_token(self):
        result, root, plan = self.prepare(
            [
                {"target": TARGET, "message": "first", "files": []},
                {"target": TARGET, "message": "second", "files": []},
            ]
        )

        markdown = Path(result["plan_path"]).read_text()
        self.assertEqual(2, result["action_count"])
        self.assertEqual(2, markdown.count(" apply --action "))
        self.assertEqual(2, markdown.count(" inspect --action "))
        self.assertNotIn("top-secret-token", markdown)
        self.assertNotIn("top-secret-token", json.dumps(plan))
        self.assertIn('```json\n"https://chat.example.com/team/channels/dev"\n```', markdown)
        self.assertIn("```markdown\nfirst\n```", markdown)
        self.assertTrue((root / "plans" / f"{result['plan_digest']}.md").is_file())
        self.assertEqual(0o700, stat.S_IMODE(root.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE((root / "current-plan.json").stat().st_mode))

    def test_file_limit_absolute_path_and_digest(self):
        file = self.root / "file.txt"
        file.write_bytes(b"payload")
        _, _root, plan = self.prepare([{"target": TARGET, "message": "", "files": [str(file)]}])
        _entry, action = self.action(plan)
        self.assertEqual(MM.hashlib.sha256(b"payload").hexdigest(), action["files"][0]["sha256"])
        with self.assertRaises(MM.MattermostError):
            self.prepare([{"target": TARGET, "message": "x", "files": ["relative"]}])
        with self.assertRaises(MM.MattermostError):
            self.prepare([{"target": TARGET, "message": "x", "files": [str(file)] * 6}])

    def run_apply(self, entry, client, mode="apply"):
        with (
            mock.patch.object(PUB.mm, "read_token", return_value="secret"),
            mock.patch.object(PUB, "PublicationClient", return_value=client),
        ):
            action, root, _path = PUB.load_action(entry["path"], entry["digest"])
            return (
                PUB.apply(action, root, entry["digest"])
                if mode == "apply"
                else PUB.inspect(action, root, entry["digest"])
            )

    def test_apply_text_only_and_repeated_success(self):
        _, _root, plan = self.prepare([{"target": TARGET, "message": "hello", "files": []}])
        entry, _action = self.action(plan)
        client = ApplyClient()

        first = self.run_apply(entry, client)
        second = self.run_apply(entry, ApplyClient())

        self.assertEqual(("applied", "applied", True), first[:3])
        self.assertEqual("hello", client.posts[0]["message"])
        self.assertEqual("already_applied", second[0])

    def test_uploads_are_recorded_and_used_in_single_post(self):
        files = []
        for name in ("one.txt", "two.txt"):
            path = self.root / name
            path.write_text(name)
            files.append(str(path))
        _, _root, plan = self.prepare([{"target": TARGET, "message": "files", "files": files}])
        entry, _action = self.action(plan)
        client = ApplyClient()

        result = self.run_apply(entry, client)

        self.assertEqual("applied", result[0])
        self.assertEqual(2, len(client.uploads))
        self.assertEqual(1, len(client.posts))
        self.assertEqual(["f" * 26, "g" * 26], client.posts[0]["file_ids"])

    def test_confirmed_upload_progress_resumes_at_next_file(self):
        files = []
        for name in ("one.txt", "two.txt"):
            path = self.root / name
            path.write_text(name)
            files.append(str(path))
        _, root, plan = self.prepare([{"target": TARGET, "message": "files", "files": files}])
        entry, _action = self.action(plan)
        first_file_id = "z" * 26
        ledger = {
            "schema_version": 1,
            "actions": {
                entry["digest"]: {
                    "status": "pending",
                    "uploads": [first_file_id],
                    "stage": None,
                }
            },
        }
        MM.replace_private(root / "publication-ledger.json", MM.canonical(ledger) + b"\n")
        client = ApplyClient()

        result = self.run_apply(entry, client)

        self.assertEqual("applied", result[0])
        self.assertEqual(1, len(client.uploads))
        self.assertEqual([first_file_id, "f" * 26], client.posts[0]["file_ids"])

    def test_ambiguous_upload_blocks_retry(self):
        file = self.root / "file.txt"
        file.write_text("payload")
        _, _root, plan = self.prepare([{"target": TARGET, "message": "file", "files": [str(file)]}])
        entry, _action = self.action(plan)
        first_client = ApplyClient(upload_error=True)

        first = self.run_apply(entry, first_client)
        second_client = ApplyClient()
        second = self.run_apply(entry, second_client)

        self.assertEqual("blocked", first[0])
        self.assertEqual("blocked", second[0])
        self.assertFalse(second[2])
        self.assertEqual([], second_client.uploads)
        _new_result, _new_root, new_plan = self.prepare(
            [{"target": TARGET, "message": "replacement", "files": []}]
        )
        PUB.load_action(entry["path"], entry["digest"])
        self.assertNotEqual(entry["digest"], new_plan["actions"][0]["digest"])

    def test_inspect_finds_ambiguous_post_by_publication_id_and_completes_ledger(self):
        _, root, plan = self.prepare([{"target": TARGET, "message": "hello", "files": []}])
        entry, action = self.action(plan)
        self.assertEqual("blocked", self.run_apply(entry, ApplyClient(create_error=True))[0])
        found = {
            "id": POST_ID,
            "channel_id": CHANNEL_ID,
            "message": "hello",
            "root_id": "",
            "file_ids": [],
            "props": {"agent_skill_publication_id": action["publication_id"]},
            "create_at": action["created_at"] * 1000,
        }

        with mock.patch.object(PUB.mm, "now", return_value=action["expires_at"] + 1):
            result = self.run_apply(entry, ApplyClient(recent=[found]), mode="inspect")

        self.assertEqual("applied", result[0])
        ledger = json.loads((root / "publication-ledger.json").read_text())
        self.assertEqual("complete", ledger["actions"][entry["digest"]]["status"])

    def test_expired_unstarted_action_is_rejected(self):
        _, _root, plan = self.prepare([{"target": TARGET, "message": "hello", "files": []}])
        entry, action = self.action(plan)

        with (
            mock.patch.object(PUB.mm, "now", return_value=action["expires_at"] + 1),
            self.assertRaises(PUB.PublicationError),
        ):
            self.run_apply(entry, ApplyClient())

    def test_preflight_failure_does_not_extend_action_ttl(self):
        _, _root, plan = self.prepare([{"target": TARGET, "message": "hello", "files": []}])
        entry, action = self.action(plan)

        class UnavailableIdentityClient(ApplyClient):
            def get(self, path):
                if path == "/users/me":
                    raise PUB.mm.MattermostError("unavailable")
                return super().get(path)

        with self.assertRaises(PUB.PublicationError):
            self.run_apply(entry, UnavailableIdentityClient())

        with (
            mock.patch.object(PUB.mm, "now", return_value=action["expires_at"] + 1),
            self.assertRaises(PUB.PublicationError),
        ):
            self.run_apply(entry, ApplyClient())

    def test_channel_inspection_pages_until_action_creation_boundary(self):
        action = {
            "channel_id": CHANNEL_ID,
            "root_id": "",
            "created_at": 100,
        }
        expected = {
            "channel_id": CHANNEL_ID,
            "message": "hello",
            "root_id": "",
            "file_ids": [],
            "props": {"agent_skill_publication_id": "publication"},
        }
        recent = [
            {
                "id": f"{index:026d}",
                "channel_id": CHANNEL_ID,
                "message": "other",
                "root_id": "",
                "file_ids": [],
                "props": {},
                "create_at": 200_000,
            }
            for index in range(200)
        ]
        found = {"id": POST_ID, "create_at": 100_000, **expected}

        class PagedClient:
            def __init__(self):
                self.calls = 0

            def get(self, _path):
                self.calls += 1
                page = recent if self.calls == 1 else [found]
                return {
                    "order": [item["id"] for item in page],
                    "posts": {item["id"]: item for item in page},
                }

        client = PagedClient()
        self.assertEqual(POST_ID, PUB.inspect_remote(client, action, expected))
        self.assertEqual(2, client.calls)

    def test_inspect_error_preserves_unknown_outcome(self):
        _, _root, plan = self.prepare([{"target": TARGET, "message": "hello", "files": []}])
        entry, _action = self.action(plan)
        self.assertEqual("blocked", self.run_apply(entry, ApplyClient(create_error=True))[0])

        class FailingInspectClient(ApplyClient):
            def get(self, path):
                if path.startswith(f"/channels/{CHANNEL_ID}/posts?"):
                    raise PUB.mm.MattermostError("unavailable")
                return super().get(path)

        result = self.run_apply(entry, FailingInspectClient(), mode="inspect")
        self.assertEqual(("blocked", "unknown", False), result[:3])

    def test_plan_escapes_untrusted_file_path(self):
        file = self.root / "value`\n# Apply: injected.txt"
        file.write_text("payload")
        result, _root, _plan = self.prepare(
            [{"target": TARGET, "message": "file", "files": [str(file)]}]
        )

        markdown = Path(result["plan_path"]).read_text()
        self.assertIn("\\n# Apply: injected.txt", markdown)
        self.assertNotIn("\n# Apply: injected.txt", markdown)

    def test_tampered_action_is_rejected(self):
        _, _root, plan = self.prepare([{"target": TARGET, "message": "hello", "files": []}])
        entry, action = self.action(plan)
        action["channel_id"] = "x" * 26
        Path(entry["path"]).write_text(json.dumps(action))
        Path(entry["path"]).chmod(0o600)

        with self.assertRaises(PUB.PublicationError):
            PUB.load_action(entry["path"], entry["digest"])

    def test_cards_prepare_apply_and_bind_full_content(self):
        for kind in ("issue", "mr"):
            for locale in ("en", "ru"):
                with self.subTest(kind=kind, locale=locale):
                    card = sample_card(kind, locale)
                    result, _, plan = self.prepare(
                        [{"target": TARGET, "message": "", "files": [], "card": card}]
                    )
                    entry, action = self.action(plan)
                    self.assertEqual(2, action["schema_version"])
                    self.assertIn(card["title"], Path(result["plan_path"]).read_text())
                    client = ApplyClient()
                    self.assertEqual("applied", self.run_apply(entry, client)[0])
                    attachment = client.posts[0]["props"]["attachments"][0]
                    self.assertEqual(card["url"], attachment["title_link"])
                    self.assertIn(
                        "ещё 2" if locale == "ru" else "2 more", attachment["fields"][-1]["value"]
                    )
                    self.assertEqual("", client.posts[0]["root_id"])
                    action["card"]["summary"] = "Changed after confirmation"
                    Path(entry["path"]).write_text(json.dumps(action))
                    with self.assertRaisesRegex(PUB.PublicationError, "tampered"):
                        PUB.load_action(entry["path"], entry["digest"])

    def test_gitlab_link_alone_remains_ordinary_message(self):
        message = "Review https://gitlab.example/team/api/-/merge_requests/248"
        _, _, plan = self.prepare([{"target": TARGET, "message": message, "files": []}])
        entry, action = self.action(plan)
        self.assertEqual(1, action["schema_version"])
        client = ApplyClient()
        self.assertEqual("applied", self.run_apply(entry, client)[0])
        self.assertEqual(message, client.posts[0]["message"])
        self.assertNotIn("attachments", client.posts[0]["props"])

    def test_card_recovery_requires_matching_attachment(self):
        _, _, plan = self.prepare(
            [{"target": TARGET, "message": "", "files": [], "card": sample_card()}]
        )
        entry, action = self.action(plan)
        self.assertEqual("blocked", self.run_apply(entry, ApplyClient(create_error=True))[0])
        expected = PUB.expected_post(action, "", [])
        found = {"id": POST_ID, "create_at": action["created_at"] * 1000, **expected}
        changed = copy.deepcopy(found)
        changed["props"]["attachments"][0]["title"] = "Different issue"
        self.assertEqual(
            "blocked", self.run_apply(entry, ApplyClient(recent=[changed]), mode="inspect")[0]
        )
        self.assertEqual(
            "applied", self.run_apply(entry, ApplyClient(recent=[found]), mode="inspect")[0]
        )

    def test_attachment_defaults_allowed_but_extra_content_rejected(self):
        expected = {
            "id": POST_ID,
            **PUB.expected_post(
                {
                    "channel_id": CHANNEL_ID,
                    "root_id": "",
                    "publication_id": "x",
                    "card": sample_card(),
                    "attachment": MM.publication_card(sample_card()),
                },
                "",
                [],
            ),
        }
        actual = copy.deepcopy(expected)
        actual["props"]["attachments"][0]["footer"] = ""
        self.assertTrue(PUB.post_matches(actual, expected))
        actual["props"]["attachments"][0]["footer"] = "Unexpected content"
        self.assertFalse(PUB.post_matches(actual, expected))
        actual = copy.deepcopy(expected)
        actual["props"]["attachments"] = []
        self.assertFalse(PUB.post_matches(actual, expected))

    def test_card_errors_precede_network_and_state(self):
        for change in ({"summary": "x" * 241}, {"actions": []}, {"locale": "de"}):
            with mock.patch.object(MM, "Client") as client:
                with self.assertRaises(MM.MattermostError):
                    MM.prepare_publication(
                        {
                            "messages": [
                                {
                                    "target": TARGET,
                                    "message": "",
                                    "files": [],
                                    "card": {**sample_card(), **change},
                                }
                            ]
                        }
                    )
                client.assert_not_called()
        self.assertFalse((self.root / "state").exists())

    def test_renderer_change_requires_new_plan(self):
        _, _, plan = self.prepare(
            [{"target": TARGET, "message": "", "files": [], "card": sample_card()}]
        )
        entry, action = self.action(plan)
        changed = {**action["attachment"], "color": "#ffffff"}
        with mock.patch.object(PUB.mm, "publication_card", return_value=changed):
            with self.assertRaisesRegex(PUB.PublicationError, "renderer changed"):
                PUB.load_action(entry["path"], entry["digest"])

    def test_card_rejects_files_body_and_existing_thread(self):
        for message, files in (("extra", []), ("", ["/file"])):
            with self.assertRaises(MM.MattermostError):
                self.prepare(
                    [{"target": TARGET, "message": message, "files": files, "card": sample_card()}]
                )
        with mock.patch.object(MM, "publication_channel", return_value={"root_id": POST_ID}):
            with self.assertRaises(MM.MattermostError):
                self.prepare(
                    [{"target": TARGET, "message": "", "files": [], "card": sample_card()}]
                )


class CardTests(unittest.TestCase):
    def test_guide_examples_are_executable_contracts(self):
        guide = (SCRIPTS.parent / "references" / "cards.md").read_text()
        examples = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", guide, re.S)]
        self.assertEqual(6, len(examples))
        for card in examples:
            with self.subTest(kind=card["kind"], locale=card["locale"], template=card["template"]):
                self.assertEqual(card["url"], MM.publication_card(card)["title_link"])

    def test_unknown_and_absent_are_distinct(self):
        for locale, unknown, absent in (("en", "Unknown", "None"), ("ru", "Неизвестно", "Нет")):
            card = sample_card(locale=locale)
            card.update(author=None, assignee="", labels=None, omitted_labels=0)
            fields = MM.publication_card(card)["fields"]
            self.assertEqual(unknown, fields[1]["value"])
            self.assertEqual(absent, fields[2]["value"])
            self.assertEqual(unknown, fields[-1]["value"])

    def test_custom_content_is_literal_not_executable_markdown(self):
        for kind in ("issue", "mr"):
            for locale in ("en", "ru"):
                card = {
                    key: value
                    for key, value in sample_card(kind, locale).items()
                    if key in {"kind", "locale", "title", "url", "summary"}
                }
                card.update(
                    template="custom",
                    summary="![image](https://example.com/x) @all",
                    fields=[{"title": "Review", "value": "**literal**", "short": False}],
                )
                result = MM.publication_card(card)
                self.assertNotIn("![image]", result["text"])
                self.assertNotIn("@all", result["text"])
                self.assertEqual(r"\*\*literal\*\*", result["fields"][0]["value"])

    def test_limits_and_localized_errors(self):
        for locale, phrase in (("en", "shorten"), ("ru", "сократите")):
            card = sample_card(locale=locale)
            card["title"] = "x" * 100
            MM.publication_card(card)
            card["title"] += "x"
            with self.assertRaisesRegex(MM.MattermostError, phrase):
                MM.publication_card(card)
            card = sample_card(locale=locale)
            card["summary"] = "x" * 240
            MM.publication_card(card)
            card["summary"] += "x"
            with self.assertRaisesRegex(MM.MattermostError, phrase):
                MM.publication_card(card)

    def test_height_budget_rejects_individually_valid_fields(self):
        card = {
            key: value
            for key, value in sample_card().items()
            if key in {"kind", "locale", "title", "url", "summary"}
        }
        card.update(
            template="custom", fields=[{"title": "Field", "value": "x" * 100, "short": False}] * 8
        )
        with self.assertRaisesRegex(MM.MattermostError, "estimated lines"):
            MM.publication_card(card)

    def test_wide_summary_has_separate_height_limit(self):
        card = sample_card()
        card["summary"] = "界" * 160
        MM.publication_card(card)
        card["summary"] += "界"
        with self.assertRaisesRegex(MM.MattermostError, "card.summary.*8 estimated lines"):
            MM.publication_card(card)

    def test_malformed_cards_fail_cleanly(self):
        for change in (
            {"labels": "bug"},
            {"labels": [None]},
            {"omitted_labels": True},
            {"omitted_labels": -1},
            {"labels": None},
            {"author": []},
            {"summary": "one\ntwo\nthree\nfour"},
            {"summary": "tab\ttext"},
            {"url": "javascript:alert(1)"},
            {"url": "https://user:pass@example.com"},
            {"url": "https://[invalid"},
            {"url": "https://example.com:bad"},
            {"locale": []},
            {"kind": {}},
            {"status": 0},
        ):
            with self.subTest(change=change), self.assertRaises(MM.MattermostError):
                MM.publication_card({**sample_card(), **change})


if __name__ == "__main__":
    unittest.main()
