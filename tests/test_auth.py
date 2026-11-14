"""Tests for OAuth2 token management (:mod:`alimail.auth`)."""

from __future__ import annotations

import json
import os
import stat
import unittest
from pathlib import Path
from unittest.mock import patch

from alimail.auth import FileTokenCache, NullCache, TokenManager, cache_key
from alimail.config import DEFAULT_BASE, SG_BASE, Credentials
from alimail.errors import AlimailError, TransportError
from tests.fakes import (
    FakeClock,
    FakeTransport,
    RecordingCache,
    json_response,
    temp_directory,
)

CUSTOM_BASE = "https://api.example.test"
APP_CREDS = Credentials(base=CUSTOM_BASE, app_id="app-id", app_secret="app-secret")
DEFAULT_HOST_CREDS = Credentials(app_id="app-id", app_secret="app-secret")
MCP_CREDS = Credentials(base=CUSTOM_BASE, token="mcp-token", email="user@example.test")
APP_CACHE_KEY = f"app-id@{CUSTOM_BASE}"


def token_response(token: str = "tok-1", *, expires_in: object = 3600, status: int = 200):
    return json_response(status, {"access_token": token, "expires_in": expires_in})


class TokenManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock(1_000_000.0)
        self.cache = RecordingCache()
        self.transport = FakeTransport([])
        self.manager = TokenManager(
            APP_CREDS,
            cache=self.cache,
            transport=self.transport,
            clock=self.clock,
            skew=120.0,
            timeout=7.0,
        )


class TokenManagerFetchTests(TokenManagerTestCase):
    def test_request_uses_the_oauth2_client_credentials_form(self):
        self.transport.push(token_response())
        self.assertEqual(self.manager.get(), "tok-1")
        call = self.transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.url, CUSTOM_BASE + "/oauth2/v2.0/token")
        self.assertEqual(
            call.form,
            {
                "grant_type": "client_credentials",
                "client_id": "app-id",
                "client_secret": "app-secret",
            },
        )
        self.assertEqual(call.headers, {"Accept": "application/json"})
        self.assertEqual(call.timeout, 7.0)

    def test_fetched_token_is_written_to_the_cache(self):
        self.transport.push(token_response())
        self.manager.get()
        self.assertEqual(len(self.cache.sets), 1)
        key, value = self.cache.sets[0]
        self.assertEqual(key, APP_CACHE_KEY)
        self.assertEqual(value["access_token"], "tok-1")
        self.assertEqual(value["expires_at"], self.clock.now + 3600)
        self.assertEqual(value["base"], CUSTOM_BASE)
        self.assertEqual(value["app_id"], "app-id")

    def test_expires_in_defaults_to_one_hour(self):
        self.transport.push(json_response(200, {"access_token": "tok"}))
        self.manager.get()
        self.assertEqual(self.cache.sets[0][1]["expires_at"], self.clock.now + 3600)

    def test_string_expires_in_is_accepted(self):
        self.transport.push(token_response(expires_in="120"))
        self.manager.get()
        self.assertEqual(self.cache.sets[0][1]["expires_at"], self.clock.now + 120)

    def test_ok_response_without_access_token_is_rejected(self):
        self.transport.push(
            json_response(200, {"expires_in": 3600}), json_response(200, {"expires_in": 3600})
        )
        manager = TokenManager(
            DEFAULT_HOST_CREDS,
            cache=self.cache,
            transport=self.transport,
            clock=self.clock,
        )
        with self.assertRaises(AlimailError):
            manager.get()
        self.assertEqual(self.transport.call_count, 2)
        self.assertEqual(self.cache.sets, [])

    def test_base_property_starts_at_the_configured_host(self):
        self.assertEqual(self.manager.base, CUSTOM_BASE)

    def test_verify_ssl_false_is_forwarded_to_token_transport(self):
        self.transport.push(token_response())
        manager = TokenManager(
            APP_CREDS,
            cache=self.cache,
            transport=self.transport,
            clock=self.clock,
            verify_ssl=False,
        )
        self.assertEqual(manager.get(), "tok-1")
        self.assertFalse(self.transport.calls[0].verify_ssl)


class TokenManagerCachingTests(TokenManagerTestCase):
    def test_valid_memory_token_is_reused(self):
        self.transport.push(token_response("tok-1"), token_response("tok-2"))
        self.assertEqual(self.manager.get(), "tok-1")
        self.assertEqual(self.manager.get(), "tok-1")
        self.assertEqual(self.transport.call_count, 1)
        # The second call is served from memory, without consulting the cache.
        self.assertEqual(self.cache.gets, [APP_CACHE_KEY])

    def test_cached_token_is_loaded_without_a_request(self):
        other_base = "https://sg.example.test"
        cache = RecordingCache(
            {
                APP_CACHE_KEY: {
                    "access_token": "cached-token",
                    "expires_at": self.clock.now + 1000,
                    "base": other_base,
                    "app_id": "app-id",
                }
            }
        )
        manager = TokenManager(
            APP_CREDS,
            cache=cache,
            transport=self.transport,
            clock=self.clock,
        )
        self.assertEqual(manager.get(), "cached-token")
        self.assertEqual(self.transport.call_count, 0)
        self.assertEqual(manager.base, other_base)
        self.assertEqual(cache.gets, [APP_CACHE_KEY])

    def test_expired_cached_token_is_refreshed(self):
        cache = RecordingCache(
            {
                APP_CACHE_KEY: {
                    "access_token": "stale",
                    "expires_at": self.clock.now - 10,
                }
            }
        )
        self.transport.push(token_response("fresh"))
        manager = TokenManager(APP_CREDS, cache=cache, transport=self.transport, clock=self.clock)
        self.assertEqual(manager.get(), "fresh")

    def test_token_is_refreshed_inside_the_skew_window(self):
        self.transport.push(token_response("tok-1", expires_in=100), token_response("tok-2"))
        self.assertEqual(self.manager.get(), "tok-1")
        self.assertEqual(self.manager.get(), "tok-2")
        self.assertEqual(self.transport.call_count, 2)

    def test_token_outside_the_skew_window_is_reused(self):
        self.transport.push(token_response("tok-1", expires_in=3600))
        self.manager.get()
        self.clock.advance(3479)
        self.assertEqual(self.manager.get(), "tok-1")
        self.assertEqual(self.transport.call_count, 1)

    def test_force_ignores_memory_and_disk_cache(self):
        self.transport.push(token_response("tok-1"), token_response("tok-2"))
        self.assertEqual(self.manager.get(), "tok-1")
        self.assertEqual(self.manager.get(force=True), "tok-2")
        self.assertEqual(self.transport.call_count, 2)
        self.assertEqual(len(self.cache.sets), 2)
        self.assertEqual(self.cache.gets, [APP_CACHE_KEY])

    def test_invalidate_clears_memory_and_disk_cache(self):
        self.transport.push(token_response("tok-1"), token_response("tok-2"))
        self.manager.get()
        self.manager.invalidate()
        self.assertEqual(self.cache.deletes, [APP_CACHE_KEY])
        self.assertEqual(self.manager.get(), "tok-2")
        self.assertEqual(self.transport.call_count, 2)


class TokenManagerFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock(1_000_000.0)
        self.cache = RecordingCache()

    def _manager(self, credentials, transport):
        return TokenManager(
            credentials,
            cache=self.cache,
            transport=transport,
            clock=self.clock,
        )

    def test_transport_failure_on_default_host_falls_back_to_singapore(self):
        transport = FakeTransport([TransportError("dns failure"), token_response("sg-token")])
        manager = self._manager(DEFAULT_HOST_CREDS, transport)
        self.assertEqual(manager.get(), "sg-token")
        self.assertEqual(
            transport.urls,
            [
                DEFAULT_BASE + "/oauth2/v2.0/token",
                SG_BASE + "/oauth2/v2.0/token",
            ],
        )
        self.assertEqual(manager.base, SG_BASE)
        self.assertEqual(self.cache.sets[0][1]["base"], SG_BASE)

    def test_http_error_on_default_host_falls_back_to_singapore(self):
        transport = FakeTransport(
            [
                json_response(400, {"error": "invalid_client"}),
                token_response("sg-token"),
            ]
        )
        manager = self._manager(DEFAULT_HOST_CREDS, transport)
        self.assertEqual(manager.get(), "sg-token")
        self.assertEqual(manager.base, SG_BASE)

    def test_explicit_base_is_not_fallback_probed(self):
        transport = FakeTransport([TransportError("dns failure")])
        manager = self._manager(APP_CREDS, transport)
        with self.assertRaises(AlimailError) as ctx:
            manager.get()
        self.assertEqual(transport.call_count, 1)
        self.assertIn(CUSTOM_BASE, str(ctx.exception))

    def test_both_hosts_failing_raises_with_details(self):
        transport = FakeTransport([TransportError("dns failure"), TransportError("tls failure")])
        manager = self._manager(DEFAULT_HOST_CREDS, transport)
        with self.assertRaises(AlimailError) as ctx:
            manager.get()
        message = str(ctx.exception)
        self.assertIn("failed to obtain access token", message)
        self.assertIn(SG_BASE, message)
        self.assertEqual(self.cache.sets, [])


class TokenManagerModeTests(unittest.TestCase):
    def test_mcp_mode_never_issues_a_network_request(self):
        transport = FakeTransport([])
        cache = RecordingCache()
        manager = TokenManager(MCP_CREDS, cache=cache, transport=transport)
        self.assertEqual(manager.get(), "mcp-token")
        self.assertEqual(manager.get(force=True), "mcp-token")
        self.assertEqual(transport.call_count, 0)
        self.assertEqual(cache.gets, [])
        self.assertEqual(cache.sets, [])

    def test_mcp_invalidate_is_a_noop(self):
        # Regression: invalidating a personal token used to clear it, so the
        # next get() tripped its internal assertion instead of returning it.
        transport = FakeTransport([])
        cache = RecordingCache()
        manager = TokenManager(MCP_CREDS, cache=cache, transport=transport)
        manager.invalidate()
        self.assertEqual(manager.get(), "mcp-token")
        self.assertEqual(manager.get(force=True), "mcp-token")
        self.assertEqual(transport.call_count, 0)
        self.assertEqual(cache.gets, [])
        self.assertEqual(cache.deletes, [])

    def test_missing_credentials_cannot_acquire_tokens(self):
        manager = TokenManager(
            Credentials(base=CUSTOM_BASE),
            cache=RecordingCache(),
            transport=FakeTransport([]),
        )
        with self.assertRaises(AlimailError) as ctx:
            manager.get()
        self.assertIn("do not support token acquisition", str(ctx.exception))


class CacheKeyTests(unittest.TestCase):
    def test_application_cache_key_is_scoped_by_app_and_base(self):
        self.assertEqual(cache_key(APP_CREDS), APP_CACHE_KEY)

    def test_mcp_cache_key_uses_the_mcp_placeholder(self):
        self.assertEqual(cache_key(MCP_CREDS), f"mcp@{CUSTOM_BASE}")


class FileTokenCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_directory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "cache" / "token-cache.json"

    def test_roundtrip_persists_between_instances(self):
        FileTokenCache(self.path).set("key", {"access_token": "tok", "expires_at": 1})
        self.assertEqual(
            FileTokenCache(self.path).get("key"),
            {"access_token": "tok", "expires_at": 1},
        )

    def test_set_creates_missing_parent_directories(self):
        cache = FileTokenCache(self.path)
        self.assertFalse(self.path.parent.exists())
        cache.set("key", {"a": 1})
        self.assertTrue(self.path.exists())

    def test_get_on_missing_file_returns_none(self):
        self.assertIsNone(FileTokenCache(self.path).get("key"))

    def test_get_on_missing_key_returns_none(self):
        cache = FileTokenCache(self.path)
        cache.set("one", {"a": 1})
        self.assertIsNone(cache.get("two"))

    def test_corrupted_file_is_treated_as_empty(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not-json{", encoding="utf-8")
        cache = FileTokenCache(self.path)
        self.assertIsNone(cache.get("key"))
        cache.set("key", {"a": 1})
        self.assertEqual(FileTokenCache(self.path).get("key"), {"a": 1})

    def test_non_dict_entry_returns_none(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"key": "just-a-string"}), encoding="utf-8")
        self.assertIsNone(FileTokenCache(self.path).get("key"))

    def test_delete_removes_only_the_requested_entry(self):
        cache = FileTokenCache(self.path)
        cache.set("one", {"a": 1})
        cache.set("two", {"b": 2})
        cache.delete("one")
        reloaded = FileTokenCache(self.path)
        self.assertIsNone(reloaded.get("one"))
        self.assertEqual(reloaded.get("two"), {"b": 2})

    def test_delete_missing_key_is_a_noop(self):
        cache = FileTokenCache(self.path)
        cache.set("one", {"a": 1})
        cache.delete("missing")
        self.assertEqual(FileTokenCache(self.path).get("one"), {"a": 1})

    def test_clear_removes_the_cache_file(self):
        cache = FileTokenCache(self.path)
        cache.set("one", {"a": 1})
        cache.clear()
        self.assertFalse(self.path.exists())
        self.assertIsNone(FileTokenCache(self.path).get("one"))

    def test_no_temporary_file_is_left_behind(self):
        cache = FileTokenCache(self.path)
        cache.set("one", {"a": 1})
        self.assertFalse(self.path.with_suffix(".tmp").exists())

    @unittest.skipUnless(os.name == "posix", "POSIX file mode bits only")
    def test_set_enforces_0700_dir_and_0600_file_permissions(self):
        self.path.parent.mkdir(parents=True, mode=0o755)
        os.chmod(self.path.parent, 0o755)
        self.path.write_text("{}", encoding="utf-8")
        os.chmod(self.path, 0o644)

        cache = FileTokenCache(self.path)
        cache.set("one", {"access_token": "secret"})

        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    @unittest.skipUnless(os.name == "posix", "POSIX file mode bits only")
    def test_delete_is_atomic_and_enforces_0600_permissions(self):
        cache = FileTokenCache(self.path)
        cache.set("one", {"a": 1})
        cache.set("two", {"b": 2})
        os.chmod(self.path, 0o644)

        with patch.object(Path, "replace", autospec=True, wraps=Path.replace) as replace_spy:
            cache.delete("one")

        self.assertEqual(replace_spy.call_count, 1)
        self.assertFalse(self.path.with_suffix(".tmp").exists())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertIsNone(cache.get("one"))
        self.assertEqual(cache.get("two"), {"b": 2})

    def test_io_errors_never_raise(self):
        cache = FileTokenCache(self.path)
        cache.set("existing", {"a": 1})
        with patch("alimail.auth.os.open", side_effect=OSError("disk full")):
            cache.set("one", {"a": 1})
            cache.delete("existing")
        with patch.object(Path, "unlink", side_effect=OSError("busy")):
            cache.clear()
        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            self.assertIsNone(cache.get("one"))


class NullCacheTests(unittest.TestCase):
    def test_null_cache_stores_nothing(self):
        cache = NullCache()
        cache.set("key", {"access_token": "tok"})
        self.assertIsNone(cache.get("key"))
        cache.delete("key")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
