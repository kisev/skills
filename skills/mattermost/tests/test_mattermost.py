#!/usr/bin/env python3

import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import stat
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mattermost.py"
SPEC = importlib.util.spec_from_file_location("mattermost_skill", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


CHANNEL_ID = "c" * 26
TEAM_ID = "t" * 26
USER_ID = "u" * 26


def post(
    post_id,
    created,
    *,
    channel_id=CHANNEL_ID,
    root_id="",
    reactions=None,
):
    return {
        "id": post_id,
        "channel_id": channel_id,
        "user_id": USER_ID,
        "root_id": root_id,
        "create_at": created,
        "update_at": created,
        "edit_at": 0,
        "delete_at": 0,
        "message": post_id,
        "reactions": reactions or [],
    }


def post_page(*items):
    return {
        "order": [item["id"] for item in items],
        "posts": {item["id"]: item for item in items},
    }


class FakeClient:
    def __init__(self, responses=None, handler=None):
        self.responses = responses or {}
        self.handler = handler
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        value = self.handler(path) if self.handler is not None else self.responses[path]
        if isinstance(value, Exception):
            raise value
        return value


class MattermostTests(unittest.TestCase):
    def cache_environment(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": directory.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        return Path(directory.name)

    def test_direct_username_is_resolved_without_search(self):
        peer_id = "p" * 26
        direct_name = "__".join(sorted((USER_ID, peer_id)))
        channel = {"id": CHANNEL_ID, "type": "D", "name": direct_name}
        client = FakeClient(
            {
                "/teams/name/team": {"id": TEAM_ID},
                "/users/username/alice": {"id": peer_id},
                f"/users/{USER_ID}/teams/{TEAM_ID}/channels": [channel],
            }
        )

        target = MODULE.classify_url("https://chat.example.com/team/messages/@alice")
        resolved = MODULE.resolve_channel(client, target, USER_ID)

        self.assertEqual(CHANNEL_ID, resolved["id"])
        self.assertNotIn("search", " ".join(client.calls))

    def test_chat_channel_id_is_resolved_directly(self):
        channel = {"id": CHANNEL_ID, "type": "G", "name": "group"}
        client = FakeClient(
            {
                "/teams/name/team": {"id": TEAM_ID},
                f"/channels/{CHANNEL_ID}": channel,
                f"/users/{USER_ID}/teams/{TEAM_ID}/channels": [channel],
            }
        )
        target = MODULE.classify_url(f"https://chat.example.com/team/group/{CHANNEL_ID}")

        self.assertEqual(channel, MODULE.resolve_channel(client, target, USER_ID))
        self.assertEqual(
            [
                "/teams/name/team",
                f"/channels/{CHANNEL_ID}",
                f"/users/{USER_ID}/teams/{TEAM_ID}/channels",
            ],
            client.calls,
        )

    def test_channels_url_resolves_direct_channel_name(self):
        peer_id = "p" * 26
        direct_name = "__".join(sorted((USER_ID, peer_id)))
        channel = {"id": CHANNEL_ID, "type": "D", "name": direct_name}
        client = FakeClient(
            {
                "/teams/name/team": {"id": TEAM_ID},
                f"/users/{USER_ID}/teams/{TEAM_ID}/channels": [channel],
            }
        )
        target = MODULE.classify_url(f"https://chat.example.com/team/channels/{direct_name}")

        self.assertEqual(channel, MODULE.resolve_channel(client, target, USER_ID))

    def test_group_route_rejects_direct_channel_name(self):
        peer_id = "p" * 26
        direct_name = "__".join(sorted((USER_ID, peer_id)))
        channel = {"id": CHANNEL_ID, "type": "D", "name": direct_name}
        client = FakeClient(
            {
                "/teams/name/team": {"id": TEAM_ID},
                f"/users/{USER_ID}/teams/{TEAM_ID}/channels": [channel],
            }
        )
        target = MODULE.classify_url(f"https://chat.example.com/team/group/{direct_name}")

        with self.assertRaises(MODULE.MattermostError):
            MODULE.resolve_channel(client, target, USER_ID)

    def test_no_reactions_omits_data_and_requests(self):
        value = post(
            "p" * 26,
            1000,
            reactions=[{"emoji_name": "yes", "user_id": USER_ID}],
        )
        client = FakeClient(handler=lambda _path: self.fail("unexpected GET"))

        posts, complete, errors = MODULE.enrich_posts(client, [value], include_reactions=False)

        self.assertTrue(complete)
        self.assertEqual([], errors)
        self.assertNotIn("reactions", posts[0])
        self.assertEqual([], client.calls)

    def test_reactions_are_requested_by_default(self):
        post_id = "p" * 26
        client = FakeClient(
            {
                f"/posts/{post_id}/reactions": [
                    {"emoji_name": "white_check_mark", "user_id": USER_ID}
                ]
            }
        )

        posts, complete, errors = MODULE.enrich_posts(
            client, [post(post_id, 1000)], include_reactions=True
        )

        self.assertTrue(complete)
        self.assertEqual([], errors)
        self.assertEqual(
            [{"emoji": "white_check_mark", "user": USER_ID}],
            posts[0]["reactions"],
        )

    def test_complete_empty_result_is_ok(self):
        result = MODULE.result_base(scope="channel")
        result.update({"complete": True, "posts": []})

        finalized = MODULE.finalize_result(result)

        self.assertEqual("ok", finalized["status"])
        self.assertTrue(finalized["complete"])
        self.assertEqual([], finalized["posts"])

    def test_read_one_returns_ok_for_empty_channel_period(self):
        def handler(path):
            if path == "/users/me":
                return {"id": USER_ID}
            if path == "/teams/name/team":
                return {"id": TEAM_ID}
            if path == f"/teams/{TEAM_ID}/channels/name/dev":
                return {"id": CHANNEL_ID, "type": "O", "name": "dev"}
            if path.startswith(f"/channels/{CHANNEL_ID}/posts?"):
                return {"order": [], "posts": {}}
            self.fail(f"unexpected GET {path}")
            return None

        client = FakeClient(handler=handler)
        with (
            mock.patch.object(MODULE, "read_token", return_value="secret"),
            mock.patch.object(MODULE, "Client", return_value=client),
            mock.patch.object(MODULE.time, "time", return_value=2000),
        ):
            result = MODULE.read_one(
                "https://chat.example.com/team/channels/dev",
                "1970-01-01T00:16:40+00:00",
                None,
                False,
                False,
            )

        self.assertEqual("ok", result["status"])
        self.assertTrue(result["complete"])
        self.assertEqual([], result["posts"])

    def test_old_root_is_added_as_context_only(self):
        root_id = "r" * 26
        reply = post("p" * 26, 2000, root_id=root_id)
        root = post(root_id, 500)
        client = FakeClient({f"/posts/{root_id}": root})

        posts, warnings, cached, fetched, age, context_roots, complete = MODULE.add_context_roots(
            client,
            [reply],
            1000,
            3000,
            None,
            read_cache=False,
            write_cache=False,
            current_ms=3000,
        )

        self.assertEqual([root_id, reply["id"]], [item["id"] for item in posts])
        self.assertTrue(posts[0]["context_only"])
        self.assertFalse(posts[1]["context_only"])
        self.assertEqual(([], 0, 1, None), (warnings, cached, fetched, age))
        self.assertEqual(1, context_roots)
        self.assertTrue(complete)

    def test_channel_uses_before_cursor(self):
        first_id = "a" * 26
        second_id = "b" * 26
        third_id = "d" * 26
        old_id = "e" * 26
        pages = [
            post_page(post(third_id, 4000), post(second_id, 3000)),
            post_page(post(first_id, 2000), post(old_id, 500)),
        ]

        def handler(_path):
            return pages.pop(0)

        client = FakeClient(handler=handler)
        with mock.patch.object(MODULE, "PAGE_SIZE", 2):
            posts, complete, count, errors, _warnings = MODULE.read_channel(
                client, {"id": CHANNEL_ID}, 1000, 5000
            )

        query = urllib.parse.parse_qs(urllib.parse.urlsplit(client.calls[1]).query)
        self.assertEqual([second_id], query["before"])
        self.assertEqual([first_id, second_id, third_id], [item["id"] for item in posts])
        self.assertTrue(complete)
        self.assertEqual(2, count)
        self.assertEqual([], errors)

    def test_posts_without_order_are_never_complete(self):
        value = {"order": [], "posts": {"p" * 26: post("p" * 26, 1000)}}

        _posts, _ordered, _order, malformed = MODULE.channel_post_page(value)

        self.assertTrue(malformed)

    def test_thread_excludes_unrelated_same_channel_posts(self):
        root_id = "r" * 26
        reply_id = "p" * 26
        unrelated_id = "x" * 26
        selected = post(reply_id, 2000, root_id=root_id)
        client = FakeClient(
            {
                f"/posts/{root_id}/thread": post_page(
                    post(root_id, 1000),
                    selected,
                    post(unrelated_id, 1500),
                )
            }
        )

        posts, complete, errors, _warnings, _hit, _age = MODULE.read_post(
            client,
            selected,
            None,
            read_cache=False,
            write_cache=False,
            current_ms=3000,
        )

        self.assertFalse(complete)
        self.assertEqual([root_id, reply_id], [item["id"] for item in posts])
        self.assertEqual("malformed_thread", errors[0]["code"])

    def test_thread_order_omission_is_partial_and_not_complete(self):
        root_id = "r" * 26
        reply_id = "p" * 26
        missing_id = "m" * 26
        selected = post(reply_id, 2000, root_id=root_id)
        client = FakeClient(
            {
                f"/posts/{root_id}/thread": {
                    "order": [root_id, reply_id, missing_id],
                    "posts": {
                        root_id: post(root_id, 1000),
                        reply_id: selected,
                    },
                }
            }
        )

        result = MODULE.read_post(
            client,
            selected,
            None,
            read_cache=False,
            write_cache=False,
            current_ms=3000,
        )

        self.assertFalse(result[1])
        self.assertEqual("malformed_thread", result[2][0]["code"])

    def test_thread_post_omitted_from_order_is_partial(self):
        root_id = "r" * 26
        reply_id = "p" * 26
        extra_id = "e" * 26
        selected = post(reply_id, 2000, root_id=root_id)
        client = FakeClient(
            {
                f"/posts/{root_id}/thread": {
                    "order": [root_id, reply_id],
                    "posts": {
                        root_id: post(root_id, 1000),
                        reply_id: selected,
                        extra_id: post(extra_id, 1500, root_id=root_id),
                    },
                }
            }
        )

        result = MODULE.read_post(
            client,
            selected,
            None,
            read_cache=False,
            write_cache=False,
            current_ms=3000,
        )

        self.assertFalse(result[1])
        self.assertEqual("malformed_thread", result[2][0]["code"])

    def test_duplicate_thread_order_is_partial(self):
        root_id = "r" * 26
        reply_id = "p" * 26
        selected = post(reply_id, 2000, root_id=root_id)
        client = FakeClient(
            {
                f"/posts/{root_id}/thread": {
                    "order": [root_id, reply_id, reply_id],
                    "posts": {
                        root_id: post(root_id, 1000),
                        reply_id: selected,
                    },
                }
            }
        )

        result = MODULE.read_post(
            client,
            selected,
            None,
            read_cache=False,
            write_cache=False,
            current_ms=3000,
        )

        self.assertFalse(result[1])
        self.assertEqual("malformed_thread", result[2][0]["code"])

    def test_cache_is_origin_and_user_isolated(self):
        root = self.cache_environment()
        current_ms = 2_000_000_000_000
        cached_post = post("p" * 26, 1000, reactions=[{"emoji_name": "x"}])
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.replace_segment(CHANNEL_ID, 0, 2000, [cached_post], current_ms - 1000)
            covered, _age = store.coverage(
                CHANNEL_ID,
                0,
                2000,
                fetched_after=None,
                current_ms=current_ms,
            )
            cached = store.posts_between(CHANNEL_ID, 0, 2000, current_ms)
        with MODULE.CacheStore("https://chat.example.com", "v" * 26) as other:
            other_covered, _age = other.coverage(
                CHANNEL_ID,
                0,
                2000,
                fetched_after=None,
                current_ms=current_ms,
            )

        path = root / "mattermost" / "cache.sqlite3"
        self.assertTrue(covered)
        self.assertFalse(other_covered)
        self.assertNotIn("reactions", cached[0])
        self.assertEqual(0o700, stat.S_IMODE(path.parent.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    def test_old_coverage_is_stable_but_not_fresh(self):
        self.cache_environment()
        current_ms = 2_000_000_000_000
        fetched_at = current_ms - 10 * 24 * 60 * 60 * 1000
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.replace_segment(CHANNEL_ID, 0, 2000, [], fetched_at)
            stable, _age = store.coverage(
                CHANNEL_ID,
                0,
                2000,
                fetched_after=None,
                current_ms=current_ms,
            )
            fresh, _age = store.coverage(
                CHANNEL_ID,
                0,
                2000,
                fetched_after=current_ms - MODULE.CACHE_TTL_SECONDS * 1000,
                current_ms=current_ms,
            )

        self.assertTrue(stable)
        self.assertFalse(fresh)

    def test_stable_channel_segment_is_served_without_post_api_request(self):
        self.cache_environment()
        current_ms = 2_000_000_000_000
        old_until = current_ms - MODULE.CACHE_STABLE_AGE_SECONDS * 1000 - 1000
        cached_post = post("p" * 26, old_until - 1000)
        client = FakeClient(handler=lambda _path: self.fail("unexpected GET"))
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.replace_segment(
                CHANNEL_ID,
                old_until - 2000,
                old_until,
                [cached_post],
                current_ms - 30 * 24 * 60 * 60 * 1000,
            )
            result = MODULE.cached_channel_posts(
                client,
                {"id": CHANNEL_ID},
                old_until - 2000,
                old_until,
                store,
                read_cache=True,
                write_cache=True,
                current_ms=current_ms,
            )

        self.assertTrue(result[1])
        self.assertTrue(result[5])
        self.assertEqual([cached_post["id"]], [item["id"] for item in result[0]])
        self.assertEqual([], client.calls)

    def test_complete_refresh_removes_deleted_posts(self):
        self.cache_environment()
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.replace_segment(CHANNEL_ID, 0, 2000, [post("p" * 26, 1000)], 2000)
            store.replace_segment(CHANNEL_ID, 0, 2000, [], 3000)
            cached = store.posts_between(CHANNEL_ID, 0, 2000)

        self.assertEqual([], cached)

    def test_stale_segment_write_cannot_replace_newer_coverage(self):
        self.cache_environment()
        post_id = "p" * 26
        newer = {**post(post_id, 1000), "update_at": 3000, "message": "new"}
        stale = {**post(post_id, 1000), "update_at": 2000, "message": "stale"}
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.replace_segment(CHANNEL_ID, 0, 2000, [newer], 3000)
            store.replace_segment(CHANNEL_ID, 0, 2000, [stale], 2000)
            cached = store.posts_between(CHANNEL_ID, 0, 2000)

        self.assertEqual("new", cached[0]["message"])

    def test_later_stale_response_cannot_replace_higher_post_activity(self):
        self.cache_environment()
        post_id = "p" * 26
        newer = {**post(post_id, 1000), "update_at": 5000, "message": "new"}
        stale = {**post(post_id, 1000), "update_at": 4000, "message": "stale"}
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.replace_segment(CHANNEL_ID, 0, 2000, [newer], 1000)
            store.replace_segment(CHANNEL_ID, 0, 2000, [stale], 2000)
            cached = store.posts_between(CHANNEL_ID, 0, 2000)

        self.assertEqual("new", cached[0]["message"])

    def test_recovered_in_period_root_invalidates_coverage(self):
        root_id = "r" * 26
        reply = post("p" * 26, 2000, root_id=root_id)

        def handler(path):
            if path == "/users/me":
                return {"id": USER_ID}
            if path == "/teams/name/team":
                return {"id": TEAM_ID}
            if path == f"/teams/{TEAM_ID}/channels/name/dev":
                return {"id": CHANNEL_ID, "type": "O", "name": "dev"}
            if path.startswith(f"/channels/{CHANNEL_ID}/posts?"):
                return post_page(reply)
            if path == f"/posts/{root_id}":
                return post(root_id, 1500)
            self.fail(f"unexpected GET {path}")
            return None

        self.cache_environment()
        client = FakeClient(handler=handler)
        with (
            mock.patch.object(MODULE, "read_token", return_value="secret"),
            mock.patch.object(MODULE, "Client", return_value=client),
            mock.patch.object(MODULE.time, "time", return_value=3),
        ):
            result = MODULE.read_one(
                "https://chat.example.com/team/channels/dev",
                "1970-01-01T00:00:01+00:00",
                None,
                True,
                True,
                include_reactions=False,
            )
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            covered, _age = store.coverage(
                CHANNEL_ID,
                1000,
                3000,
                fetched_after=None,
                current_ms=3000,
            )
            cached_root = store.get_post(root_id, 3000)

        self.assertEqual("partial", result["status"])
        self.assertFalse(covered)
        self.assertIsNotNone(cached_root)

    def test_partial_read_does_not_create_coverage(self):
        self.cache_environment()
        current_ms = 2_000_000_000_000
        client = FakeClient(handler=lambda _path: MODULE.MattermostError("offline"))
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            result = MODULE.cached_channel_posts(
                client,
                {"id": CHANNEL_ID},
                current_ms - 1000,
                current_ms,
                store,
                read_cache=True,
                write_cache=True,
                current_ms=current_ms,
            )
            covered, _age = store.coverage(
                CHANNEL_ID,
                current_ms - 1000,
                current_ms,
                fetched_after=None,
                current_ms=current_ms,
            )

        self.assertFalse(result[1])
        self.assertFalse(covered)

    def test_version_zero_snapshot_cache_is_migrated(self):
        root = self.cache_environment()
        path = root / "mattermost" / "cache.sqlite3"
        path.parent.mkdir(mode=0o700)
        with sqlite3.connect(path) as database:
            database.execute("CREATE TABLE snapshots_v2 (key TEXT PRIMARY KEY)")
        path.chmod(0o600)

        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            version = store.database.execute("PRAGMA user_version").fetchone()[0]
            old_table = store.database.execute(
                "SELECT name FROM sqlite_master WHERE name='snapshots_v2'"
            ).fetchone()

        self.assertEqual(MODULE.CACHE_SCHEMA_VERSION, version)
        self.assertIsNone(old_table)

    def test_unsupported_cache_schema_stops(self):
        root = self.cache_environment()
        path = root / "mattermost" / "cache.sqlite3"
        path.parent.mkdir(mode=0o700)
        with sqlite3.connect(path) as database:
            database.execute("PRAGMA user_version=99")
        path.chmod(0o600)

        with self.assertRaises(MODULE.CacheError):
            MODULE.CacheStore("https://chat.example.com", USER_ID)

    def test_cache_schema_without_primary_keys_stops(self):
        root = self.cache_environment()
        path = root / "mattermost" / "cache.sqlite3"
        path.parent.mkdir(mode=0o700)
        with sqlite3.connect(path) as database:
            database.execute(
                """CREATE TABLE posts_v3 (
                origin TEXT, user_id TEXT, post_id TEXT, channel_id TEXT,
                root_id TEXT, create_at INTEGER, activity_at INTEGER,
                fetched_at INTEGER, payload TEXT)"""
            )
            database.execute(f"PRAGMA user_version={MODULE.CACHE_SCHEMA_VERSION}")
        path.chmod(0o600)

        with self.assertRaises(MODULE.CacheError):
            MODULE.CacheStore("https://chat.example.com", USER_ID)

    def test_fresh_complete_thread_snapshot_is_reused(self):
        self.cache_environment()
        current_ms = 2_000_000_000_000
        root_id = "r" * 26
        reply_id = "p" * 26
        root = post(root_id, current_ms - 2000)
        reply = post(reply_id, current_ms - 1000, root_id=root_id)
        client = FakeClient(handler=lambda _path: self.fail("unexpected GET"))
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.put_thread(root_id, [root, reply], current_ms - 1000, complete=True)
            result = MODULE.read_post(
                client,
                reply,
                store,
                read_cache=True,
                write_cache=True,
                current_ms=current_ms,
            )

        self.assertTrue(result[1])
        self.assertTrue(result[4])
        self.assertEqual([root_id, reply_id], [item["id"] for item in result[0]])
        self.assertEqual([], client.calls)

    def test_revalidated_post_updates_cached_thread_payload(self):
        self.cache_environment()
        current_ms = 2_000_000_000_000
        root_id = "r" * 26
        cached_root = {**post(root_id, current_ms - 2000), "message": "old"}
        current_root = {
            **cached_root,
            "message": "new",
            "update_at": current_ms - 500,
        }
        client = FakeClient(handler=lambda _path: self.fail("unexpected GET"))
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.put_thread(root_id, [cached_root], current_ms - 1000, complete=True)
            result = MODULE.read_post(
                client,
                current_root,
                store,
                read_cache=True,
                write_cache=True,
                current_ms=current_ms,
            )
            cached = store.get_post(root_id, current_ms)

        self.assertTrue(result[4])
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertEqual("new", cached[0]["message"])

    def test_corrupt_cache_stops_instead_of_falling_back(self):
        root = self.cache_environment()
        path = root / "mattermost" / "cache.sqlite3"
        path.parent.mkdir(mode=0o700)
        path.write_text("not sqlite", encoding="utf-8")
        path.chmod(0o600)

        with self.assertRaises(MODULE.CacheError):
            MODULE.CacheStore("https://chat.example.com", USER_ID)

    def test_cache_payload_index_mismatch_stops(self):
        self.cache_environment()
        post_id = "p" * 26
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.put_posts([post(post_id, 1000)], 2000)
            payload = json.dumps({**post(post_id, 1000), "channel_id": "x" * 26})
            store.database.execute(
                "UPDATE posts_v3 SET payload=? WHERE post_id=?", (payload, post_id)
            )
            store.database.commit()
            with self.assertRaises(MODULE.CacheError):
                store.get_post(post_id)

    def test_parent_cookie_domain_and_agent_browser_wrapper_are_supported(self):
        payload = {
            "success": True,
            "data": {
                "cookies": [
                    {
                        "name": "MMAUTHTOKEN",
                        "domain": ".example.com",
                        "value": "parent-token",
                    },
                    {
                        "name": "MMAUTHTOKEN",
                        "domain": "unrelated.example.net",
                        "value": "wrong-token",
                    },
                ]
            },
        }

        token = MODULE.token_from_cookies("https://chat.example.com", payload)

        self.assertEqual("parent-token", token)

    def test_exact_cookie_domain_is_preferred_over_parent(self):
        payload = [
            {
                "name": "MMAUTHTOKEN",
                "domain": ".example.com",
                "value": "parent-token",
            },
            {
                "name": "MMAUTHTOKEN",
                "domain": "chat.example.com",
                "value": "exact-token",
            },
        ]

        self.assertEqual(
            "exact-token",
            MODULE.token_from_cookies("https://chat.example.com", payload),
        )

    def test_host_only_parent_cookie_does_not_match_subdomain(self):
        payload = [
            {
                "name": "MMAUTHTOKEN",
                "domain": "example.com",
                "value": "host-only-token",
            }
        ]

        with self.assertRaises(MODULE.MattermostError):
            MODULE.token_from_cookies("https://chat.example.com", payload)

    def test_expired_exact_cookie_does_not_override_current_parent(self):
        payload = [
            {
                "name": "MMAUTHTOKEN",
                "domain": ".example.com",
                "value": "parent-token",
                "expires": 200,
            },
            {
                "name": "MMAUTHTOKEN",
                "domain": "chat.example.com",
                "value": "expired-token",
                "expires": 99,
            },
        ]

        with mock.patch.object(MODULE, "now", return_value=100):
            token = MODULE.token_from_cookies("https://chat.example.com", payload)

        self.assertEqual("parent-token", token)

    def test_failed_cookie_wrapper_is_rejected(self):
        payload = {
            "success": False,
            "data": {
                "cookies": [
                    {
                        "name": "MMAUTHTOKEN",
                        "domain": "chat.example.com",
                        "value": "token",
                    }
                ]
            },
        }

        with self.assertRaises(MODULE.MattermostError):
            MODULE.token_from_cookies("https://chat.example.com", payload)

    def test_failed_nested_cookie_wrapper_is_rejected(self):
        payload = {
            "success": True,
            "data": {
                "success": False,
                "cookies": [
                    {
                        "name": "MMAUTHTOKEN",
                        "domain": "chat.example.com",
                        "value": "token",
                    }
                ],
            },
        }

        with self.assertRaises(MODULE.MattermostError):
            MODULE.token_from_cookies("https://chat.example.com", payload)

    def test_malformed_cookie_expiry_is_rejected(self):
        for expires in ("invalid", float("inf")):
            with self.subTest(expires=expires):
                payload = [
                    {
                        "name": "MMAUTHTOKEN",
                        "domain": "chat.example.com",
                        "value": "token",
                        "expires": expires,
                    }
                ]
                with self.assertRaises(MODULE.MattermostError):
                    MODULE.token_from_cookies("https://chat.example.com", payload)

    def test_future_cache_post_timestamp_stops(self):
        self.cache_environment()
        with MODULE.CacheStore("https://chat.example.com", USER_ID) as store:
            store.put_posts([post("p" * 26, 1000)], 3000)
            with self.assertRaises(MODULE.CacheError):
                store.get_post("p" * 26, 2000)

    def test_authorization_failure_during_reactions_propagates(self):
        client = FakeClient(handler=lambda _path: MODULE.AuthorizationRequired("expired"))

        with self.assertRaises(MODULE.AuthorizationRequired):
            MODULE.read_reactions(client, [post("p" * 26, 1000)])

    def test_read_token_rejects_unsafe_mode_and_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
                path = MODULE.origin_token_file("https://chat.example.com")
                path.parent.mkdir(parents=True, mode=0o700)
                path.parent.parent.chmod(0o700)
                path.write_text("secret\n", encoding="utf-8")
                path.chmod(0o644)
                with self.assertRaises(MODULE.AuthorizationRequired):
                    MODULE.read_token("https://chat.example.com")
                self.assertEqual(0o644, stat.S_IMODE(path.stat().st_mode))
                path.chmod(0o600)
                os.link(path, path.with_name("token-link"))
                with self.assertRaises(MODULE.AuthorizationRequired):
                    MODULE.read_token("https://chat.example.com")

    def test_auth_validates_browser_token_before_save(self):
        events = []
        client = FakeClient({"/users/me": {"id": USER_ID}})

        def receipt(*_args, consume=True, **_kwargs):
            events.append("consume" if consume else "validate-receipt")

        with (
            mock.patch.object(MODULE, "consume_receipt", side_effect=receipt),
            mock.patch.object(MODULE, "agent_browser_token", return_value="secret"),
            mock.patch.object(MODULE, "Client", return_value=client),
            mock.patch.object(
                MODULE, "save_token", side_effect=lambda *_args: events.append("save")
            ),
            mock.patch.object(MODULE, "mark_local_mutation"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = MODULE.main(
                [
                    "auth",
                    "apply",
                    "https://chat.example.com/team/channels/dev",
                    "--confirm",
                    "a" * 64,
                    "--browser-consent",
                ]
            )

        self.assertEqual(0, code)
        self.assertEqual(["validate-receipt", "consume", "save"], events)
        self.assertEqual(["/users/me"], client.calls)

    def test_auth_path_reports_origin_bound_file_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}),
                contextlib.redirect_stdout(output),
            ):
                code = MODULE.main(["auth", "path", "https://chat.example.com/team/channels/dev"])

            result = json.loads(output.getvalue())
            self.assertEqual(0, code)
            self.assertEqual("0600", result["file_mode"])
            self.assertEqual("0700", result["directory_mode"])
            self.assertFalse(Path(result["token_path"]).exists())

    def test_cli_no_reactions_passes_flag_to_reader(self):
        completed = {
            **MODULE.result_base(scope="post"),
            "status": "ok",
            "complete": True,
            "posts": [post("p" * 26, 1000)],
        }
        output = io.StringIO()
        with (
            mock.patch.object(MODULE, "read_one", return_value=completed) as read_one,
            contextlib.redirect_stdout(output),
        ):
            exit_code = MODULE.main(
                ["read", f"https://chat.example.com/team/pl/{'p' * 26}", "--no-reactions"]
            )

        self.assertEqual(0, exit_code)
        self.assertFalse(read_one.call_args.kwargs["include_reactions"])
        self.assertEqual("ok", json.loads(output.getvalue())["status"])

    def test_cli_reports_cache_error_with_distinct_exit(self):
        output = io.StringIO()
        with (
            mock.patch.object(MODULE, "read_one", side_effect=MODULE.CacheError("broken")),
            contextlib.redirect_stdout(output),
        ):
            exit_code = MODULE.main(["read", f"https://chat.example.com/team/pl/{'p' * 26}"])

        result = json.loads(output.getvalue())
        self.assertEqual(MODULE.CACHE_ERROR_EXIT, exit_code)
        self.assertEqual("cache_error", result["errors"][0]["code"])


if __name__ == "__main__":
    unittest.main()
