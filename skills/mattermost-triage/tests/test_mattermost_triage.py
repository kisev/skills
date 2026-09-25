#!/usr/bin/env python3

import importlib.util
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from argparse import Namespace
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


TRIAGE = load("mattermost_triage_test", SCRIPTS / "mattermost_triage.py")
PUBLICATION = load(
    "mattermost_triage_publication_test",
    SCRIPTS / "mattermost_triage_publication.py",
)

ORIGIN = "https://chat.example.com"
USER_ID = "u" * 26
PEER_ID = "v" * 26
TEAM_ID = "t" * 26
TEAM_TWO_ID = "s" * 26
CHANNEL_ID = "c" * 26
ROOT_ID = "r" * 26
REPLY_ID = "p" * 26
PUBLISHED_ID = "z" * 26


def user(user_id, username):
    return {
        "id": user_id,
        "username": username,
        "first_name": username.title(),
        "last_name": "User",
        "nickname": "",
    }


def post(post_id, message, created, root_id=""):
    return {
        "id": post_id,
        "channel_id": CHANNEL_ID,
        "user_id": PEER_ID,
        "root_id": root_id,
        "create_at": created,
        "update_at": created,
        "delete_at": 0,
        "message": message,
        "file_ids": ["must-not-survive"],
        "metadata": {"files": [{"name": "secret.txt"}]},
    }


def page(*posts):
    return {"order": [item["id"] for item in posts], "posts": {item["id"]: item for item in posts}}


class CollectionClient:
    def __init__(self, *, reaction_error=False, failed_teams=None, unavailable_posts=None):
        self.reaction_error = reaction_error
        self.failed_teams = set(failed_teams or [])
        self.unavailable_posts = set(unavailable_posts or [])
        self.calls = []
        self.root = post(ROOT_ID, "Need an answer", 1_767_225_600_000)
        self.reply = post(REPLY_ID, "Extra uncited context", 1_767_225_700_000, ROOT_ID)

    def get(self, path):
        self.calls.append(path)
        if path == "/users/me":
            return user(USER_ID, "current")
        if path == f"/users/{USER_ID}/teams":
            return [
                {"id": TEAM_TWO_ID, "name": "z-team"},
                {"id": TEAM_ID, "name": "team"},
            ]
        if path in {
            f"/users/{USER_ID}/teams/{TEAM_ID}/channels",
            f"/users/{USER_ID}/teams/{TEAM_TWO_ID}/channels",
        }:
            team_id = path.split("/")[-2]
            if team_id in self.failed_teams:
                raise TRIAGE.TriageError("team listing unavailable")
            return [
                {
                    "id": CHANNEL_ID,
                    "name": "__".join(sorted((USER_ID, PEER_ID))),
                    "display_name": "Direct",
                    "type": "D",
                    "team_id": "",
                    "last_post_at": self.reply["create_at"],
                }
            ]
        if path == f"/channels/{CHANNEL_ID}":
            return {
                "id": CHANNEL_ID,
                "name": "__".join(sorted((USER_ID, PEER_ID))),
                "display_name": "Direct",
                "type": "D",
                "team_id": "",
                "last_post_at": self.reply["create_at"],
            }
        if path == f"/posts/{ROOT_ID}":
            if ROOT_ID in self.unavailable_posts:
                raise TRIAGE.TriageError("post unavailable")
            return self.root
        if path == f"/posts/{REPLY_ID}":
            if REPLY_ID in self.unavailable_posts:
                raise TRIAGE.TriageError("post unavailable")
            return self.reply
        if path.startswith(f"/channels/{CHANNEL_ID}/posts?"):
            return page(self.root)
        if path == f"/posts/{ROOT_ID}/thread":
            return page(self.root, self.reply)
        if path in {f"/posts/{ROOT_ID}/reactions", f"/posts/{REPLY_ID}/reactions"}:
            if self.reaction_error and path.endswith(f"{ROOT_ID}/reactions"):
                raise TRIAGE.TriageError("reaction endpoint unavailable")
            return [{"emoji_name": "+1", "user_id": USER_ID}]
        if path == f"/users/{PEER_ID}":
            return user(PEER_ID, "peer")
        raise AssertionError(f"unexpected GET {path}")


class ApplyClient:
    def __init__(self, *, ambiguous=False, not_applied=False, recovered=None):
        self.ambiguous = ambiguous
        self.not_applied = not_applied
        self.recovered = recovered or []
        self.posts = []

    def post_text(self, payload):
        self.posts.append(payload)
        if self.ambiguous:
            raise PUBLICATION.AmbiguousPost("unknown")
        if self.not_applied:
            raise PUBLICATION.NotApplied(400)
        return {"id": PUBLISHED_ID, **payload}

    def get(self, path):
        if path == f"/posts/{PUBLISHED_ID}":
            return {"id": PUBLISHED_ID, **self.posts[-1]}
        if path.startswith(f"/channels/{CHANNEL_ID}/posts?"):
            return page(*self.recovered)
        raise AssertionError(f"unexpected GET {path}")


class MattermostTriageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = mock.patch.dict(
            os.environ,
            {
                "XDG_STATE_HOME": str(self.root / "state"),
                "XDG_CONFIG_HOME": str(self.root / "config"),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def collect(
        self,
        *,
        reaction_error=False,
        failed_teams=None,
        unavailable_posts=None,
        targets=None,
        limit=20,
        since="2026-01-01T00:00:00Z",
        until="2026-01-02T00:00:00Z",
    ):
        client = CollectionClient(
            reaction_error=reaction_error,
            failed_teams=failed_teams,
            unavailable_posts=unavailable_posts,
        )
        args = Namespace(
            origin=ORIGIN,
            limit=limit,
            target=targets or [],
            since=since,
            until=until,
        )
        with (
            mock.patch.object(TRIAGE, "read_token", return_value="secret"),
            mock.patch.object(TRIAGE, "Client", return_value=client),
        ):
            result, code = TRIAGE.collect(args)
        evidence = json.loads(Path(result["evidence_path"]).read_text())
        return result, code, evidence, client

    def analysis(
        self,
        digest,
        *,
        quote="Need an answer",
        status="attention",
        closure=None,
        draft="I will check.",
    ):
        if closure is None:
            closure = {"attention": "open", "disputed": "uncertain", "no_action": "closed"}[status]
        return {
            "schema_version": 1,
            "evidence_digest": digest,
            "summary": {"confidence": "high", "rationale": "The request is explicit."},
            "candidates": [
                {
                    "id": "reply-needed",
                    "status": status,
                    "closure": closure,
                    "confidence": "high",
                    "rationale": "A direct request has no answer.",
                    "source_post_ids": [ROOT_ID],
                    "cited_excerpts": [{"post_id": ROOT_ID, "quote": quote}],
                    "draft_response": draft,
                    "response_target": f"{ORIGIN}/team/messages/{CHANNEL_ID}" if draft else None,
                    "plan": None if draft else "Wait for more evidence.",
                }
            ],
        }

    def publish_analysis(self, result, analysis):
        path = self.root / "analysis-input.json"
        path.write_text(json.dumps(analysis))
        return TRIAGE.publish(Namespace(evidence=result["current_path"], analysis=str(path)))

    def test_collect_keeps_full_threads_profiles_literal_reactions_and_no_attachments(self):
        result, code, evidence, client = self.collect()

        self.assertEqual(0, code)
        self.assertTrue(result["complete"])
        self.assertEqual([ROOT_ID, REPLY_ID], [item["id"] for item in evidence["posts"]])
        self.assertEqual([{"emoji": "+1", "user_id": USER_ID}], evidence["posts"][0]["reactions"])
        self.assertEqual([USER_ID, PEER_ID], sorted(item["id"] for item in evidence["profiles"]))
        self.assertNotIn("file_ids", json.dumps(evidence))
        self.assertNotIn("secret.txt", json.dumps(evidence))
        self.assertIn(f"/posts/{ROOT_ID}/thread", client.calls)
        self.assertIn(f"/users/{USER_ID}/teams/{TEAM_ID}/channels", client.calls)
        self.assertIn(f"/users/{USER_ID}/teams/{TEAM_TWO_ID}/channels", client.calls)
        self.assertNotIn(f"/users/{USER_ID}/channels", client.calls)
        self.assertEqual(1, result["counts"]["sources"])
        self.assertTrue(all(item["thread_complete"] for item in evidence["post_provenance"]))
        self.assertEqual(0o600, Path(result["evidence_path"]).stat().st_mode & 0o777)

    def test_team_listing_errors_are_partial_and_successful_teams_survive(self):
        result, code, evidence, _client = self.collect(failed_teams={TEAM_TWO_ID})

        self.assertEqual(1, code)
        self.assertFalse(result["complete"])
        self.assertEqual([ROOT_ID, REPLY_ID], [item["id"] for item in evidence["posts"]])
        self.assertIn("team_channels_unavailable", {item["code"] for item in evidence["errors"]})

        result, code, evidence, _client = self.collect(failed_teams={TEAM_ID, TEAM_TWO_ID})
        self.assertEqual(1, code)
        self.assertEqual([], evidence["posts"])
        self.assertIn("no_team_channel_lists", {item["code"] for item in evidence["errors"]})

    def test_permalink_collects_only_its_full_thread_outside_period(self):
        target = f"{ORIGIN}/team/pl/{REPLY_ID}"
        _result, code, evidence, client = self.collect(
            targets=[target],
            limit=0,
            since="2027-01-01T00:00:00Z",
            until="2027-01-02T00:00:00Z",
        )

        self.assertEqual(0, code)
        self.assertEqual([ROOT_ID, REPLY_ID], [item["id"] for item in evidence["posts"]])
        self.assertEqual(target, evidence["sources"][0]["target"])
        self.assertEqual(CHANNEL_ID, evidence["sources"][0]["channel"]["id"])
        self.assertEqual("explicit_permalink", evidence["sources"][0]["selection"])
        self.assertFalse(
            any(call.startswith(f"/channels/{CHANNEL_ID}/posts?") for call in client.calls)
        )

    def test_partial_reactions_are_surfaced_without_losing_messages(self):
        result, code, evidence, _client = self.collect(reaction_error=True)

        self.assertEqual(1, code)
        self.assertFalse(result["complete"])
        self.assertEqual([ROOT_ID, REPLY_ID], [item["id"] for item in evidence["posts"]])
        self.assertEqual([], evidence["posts"][0]["reactions"])
        self.assertIn("reactions_unavailable", {item["code"] for item in evidence["errors"]})

    def test_next_collection_uses_last_complete_until(self):
        _first, _code, _evidence, _client = self.collect()
        _partial, partial_code, _evidence, _client = self.collect(reaction_error=True)
        _second, _code, evidence, _client = self.collect(since=None, until="2026-01-03T00:00:00Z")

        self.assertEqual(1, partial_code)
        self.assertEqual("2026-01-02T00:00:00Z", evidence["period"]["since"])

    def test_explicit_since_still_collects_open_candidate_carryover(self):
        collected, _code, _evidence, _client = self.collect()
        self.publish_analysis(collected, self.analysis(collected["evidence_digest"]))

        _result, code, evidence, client = self.collect(
            limit=0,
            since="2027-01-01T00:00:00Z",
            until="2027-01-02T00:00:00Z",
        )

        self.assertEqual(0, code)
        self.assertEqual([ROOT_ID, REPLY_ID], [item["id"] for item in evidence["posts"]])
        self.assertEqual("carryover_unresolved", evidence["sources"][0]["selection"])
        self.assertEqual(["reply-needed"], evidence["sources"][0]["carryover_candidate_ids"])
        self.assertIn(f"/posts/{ROOT_ID}", client.calls)

    def test_unavailable_carryover_is_partial(self):
        collected, _code, _evidence, _client = self.collect()
        self.publish_analysis(collected, self.analysis(collected["evidence_digest"]))

        _result, code, evidence, _client = self.collect(
            limit=0,
            unavailable_posts={ROOT_ID},
            since="2027-01-01T00:00:00Z",
            until="2027-01-02T00:00:00Z",
        )

        self.assertEqual(1, code)
        self.assertFalse(evidence["complete"])
        self.assertIn("carryover_unavailable", {item["code"] for item in evidence["errors"]})

    def test_tampered_analysis_pointer_is_not_used_for_carryover(self):
        collected, _code, _evidence, _client = self.collect()
        published, _code = self.publish_analysis(
            collected, self.analysis(collected["evidence_digest"])
        )
        pointer = Path(published["current_path"])
        value = json.loads(pointer.read_text())
        value["path"] = str(self.root / "outside.json")
        pointer.write_text(json.dumps(value))

        _result, code, evidence, _client = self.collect(
            limit=0,
            since="2027-01-01T00:00:00Z",
            until="2027-01-02T00:00:00Z",
        )

        self.assertEqual(1, code)
        self.assertEqual([], evidence["posts"])
        self.assertIn("carryover_state_invalid", {item["code"] for item in evidence["errors"]})

    def test_publish_keeps_only_citations_and_writes_one_manual_command(self):
        collected, _code, _evidence, _client = self.collect()
        result, code = self.publish_analysis(collected, self.analysis(collected["evidence_digest"]))

        durable = json.loads(Path(result["analysis_path"]).read_text())
        report = Path(result["report_path"]).read_text()
        self.assertEqual(0, code)
        self.assertNotIn("Extra uncited context", json.dumps(durable))
        self.assertIn("Need an answer", json.dumps(durable))
        self.assertEqual(1, result["primary_attention_count"])
        self.assertEqual(1, len(result["publication_commands"]))
        self.assertEqual(1, report.count("mattermost_triage_publication.py publish"))
        self.assertIn("--confirm", result["publication_commands"][0]["command"])

    def test_publish_rejects_nonliteral_quote_and_disputed_draft(self):
        collected, _code, _evidence, _client = self.collect()
        with self.assertRaises(TRIAGE.TriageError):
            self.publish_analysis(
                collected, self.analysis(collected["evidence_digest"], quote="invented")
            )
        with self.assertRaises(TRIAGE.TriageError):
            self.publish_analysis(
                collected,
                self.analysis(collected["evidence_digest"], status="disputed"),
            )

    def test_closure_contract_and_incomplete_draft_rejection(self):
        collected, _code, _evidence, _client = self.collect()
        with self.assertRaises(TRIAGE.TriageError):
            self.publish_analysis(
                collected,
                self.analysis(collected["evidence_digest"], closure="closed"),
            )

        partial, _code, _evidence, _client = self.collect(reaction_error=True)
        with self.assertRaises(TRIAGE.TriageError):
            self.publish_analysis(partial, self.analysis(partial["evidence_digest"]))
        result, code = self.publish_analysis(
            partial,
            self.analysis(
                partial["evidence_digest"],
                status="disputed",
                closure="uncertain",
                draft=None,
            ),
        )
        durable = json.loads(Path(result["analysis_path"]).read_text())
        self.assertEqual(1, code)
        self.assertEqual("uncertain", durable["candidates"][0]["closure"])

    def test_publication_posts_once_and_is_idempotent(self):
        collected, _code, _evidence, _client = self.collect()
        published, _code = self.publish_analysis(
            collected, self.analysis(collected["evidence_digest"])
        )
        entry = published["publication_commands"][0]
        action, root, digest = PUBLICATION.load_action(entry["path"], entry["digest"])
        client = ApplyClient()

        with mock.patch.object(PUBLICATION, "revalidate", return_value=client):
            first = PUBLICATION.publish(action, root, digest)
            second = PUBLICATION.publish(action, root, digest)

        self.assertEqual(("applied", "applied", True), first[:3])
        self.assertEqual("already_applied", second[0])
        self.assertEqual(1, len(client.posts))
        self.assertEqual(
            action["publication_id"],
            client.posts[0]["props"]["agent_skill_publication_id"],
        )

    def test_publication_action_is_deterministic_and_expires_before_remote_get(self):
        collected, _code, evidence, _client = self.collect()
        analysis = self.analysis(collected["evidence_digest"])
        first, _code = self.publish_analysis(collected, analysis)
        second, _code = self.publish_analysis(collected, analysis)
        first_entry = first["publication_commands"][0]
        second_entry = second["publication_commands"][0]
        action, root, digest = PUBLICATION.load_action(first_entry["path"], first_entry["digest"])

        self.assertEqual(first_entry["digest"], second_entry["digest"])
        self.assertEqual(
            int(TRIAGE.aware_instant(evidence["collected_at"], "collected_at").timestamp()),
            action["created_at"],
        )
        self.assertEqual(action["created_at"] + 86_400, action["expires_at"])
        with (
            mock.patch.object(PUBLICATION.time, "time", return_value=action["expires_at"]),
            mock.patch.object(PUBLICATION, "revalidate") as revalidate,
            self.assertRaises(PUBLICATION.PublicationError),
        ):
            PUBLICATION.publish(action, root, digest)
        revalidate.assert_not_called()

    def test_ambiguous_publication_blocks_then_recovers_by_hidden_id(self):
        collected, _code, _evidence, _client = self.collect()
        published, _code = self.publish_analysis(
            collected, self.analysis(collected["evidence_digest"])
        )
        entry = published["publication_commands"][0]
        action, root, digest = PUBLICATION.load_action(entry["path"], entry["digest"])
        ambiguous = ApplyClient(ambiguous=True)
        expected = PUBLICATION.expected_payload(action)
        recovered = ApplyClient(recovered=[{"id": PUBLISHED_ID, **expected}])

        with mock.patch.object(PUBLICATION, "revalidate", return_value=ambiguous):
            first = PUBLICATION.publish(action, root, digest)
        with mock.patch.object(PUBLICATION, "revalidate", return_value=recovered):
            second = PUBLICATION.publish(action, root, digest)

        self.assertEqual(("blocked", "unknown", True), first[:3])
        self.assertEqual(("applied", "applied", False), second[:3])
        self.assertTrue(second[3]["recovered"])
        self.assertEqual([], recovered.posts)

    def test_definitive_http_400_is_not_applied(self):
        client = PUBLICATION.PublicationClient.__new__(PUBLICATION.PublicationClient)
        client.origin = ORIGIN
        client.token = "secret"
        client.opener = mock.Mock()
        client.opener.open.side_effect = urllib.error.HTTPError(
            f"{ORIGIN}/api/v4/posts", 400, "bad request", None, None
        )

        with self.assertRaises(PUBLICATION.NotApplied) as caught:
            client.post_text({"channel_id": CHANNEL_ID, "message": "text", "props": {}})

        self.assertEqual(400, caught.exception.status)

    def test_definitive_rejection_has_not_applied_outcome(self):
        collected, _code, _evidence, _client = self.collect()
        published, _code = self.publish_analysis(
            collected, self.analysis(collected["evidence_digest"])
        )
        entry = published["publication_commands"][0]
        action, root, digest = PUBLICATION.load_action(entry["path"], entry["digest"])

        with mock.patch.object(
            PUBLICATION, "revalidate", return_value=ApplyClient(not_applied=True)
        ):
            result = PUBLICATION.publish(action, root, digest)

        self.assertEqual(("not_applied", "not_applied", False), result[:3])
        self.assertEqual(400, result[3]["http_status"])

    def test_capabilities_and_aware_timestamp_validation(self):
        self.assertEqual(["collect", "publish"], TRIAGE.capabilities()["commands"])
        with self.assertRaises(TRIAGE.TriageError):
            TRIAGE.aware_instant("2026-01-01T00:00:00", "--since")
        with self.assertRaises(TRIAGE.TriageError):
            TRIAGE.normalized_origin("http://chat.example.com")


if __name__ == "__main__":
    unittest.main()
