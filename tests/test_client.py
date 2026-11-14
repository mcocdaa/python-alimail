"""Tests for :class:`alimail.client.Client`."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from alimail.auth import NullCache
from alimail.client import DEFAULT_BACKOFF, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, Client
from alimail.config import DEFAULT_BASE, SG_BASE, Credentials
from alimail.errors import (
    AlimailError,
    AuthError,
    NotFound,
    PermissionDenied,
    RateLimitError,
    ServerError,
    TransportError,
)
from tests.fakes import (
    APP_BASE,
    FakeTransport,
    json_response,
    make_client,
    url_path,
    url_query,
)

TOKEN_VALUE = "test-access-token"


class ClientConstructionTests(unittest.TestCase):
    def test_load_credentials_receives_the_constructor_arguments(self):
        credentials = Credentials(base=APP_BASE, token="tok", email="user@example.test")
        with patch("alimail.client.load_credentials", return_value=credentials) as loader:
            client = Client(
                app_id="app-id",
                app_secret="app-secret",
                base=APP_BASE,
                token="tok",
                email="user@example.test",
                transport=FakeTransport([]),
                cache=NullCache(),
            )
        loader.assert_called_once_with(
            app_id="app-id",
            app_secret="app-secret",
            base=APP_BASE,
            token="tok",
            email="user@example.test",
        )
        self.assertEqual(client.mode, "mcp")
        self.assertEqual(client.email, "user@example.test")

    def test_from_env_forwards_keyword_arguments(self):
        credentials = Credentials(base=APP_BASE, app_id="a", app_secret="s")
        with patch("alimail.client.load_credentials", return_value=credentials):
            client = Client.from_env(
                app_id="a", app_secret="s", transport=FakeTransport([]), cache=NullCache()
            )
        self.assertEqual(client.mode, "app")
        self.assertEqual(client.base, APP_BASE)

    def test_from_mcp_token_builds_a_bearer_token_client(self):
        credentials = Credentials(base=APP_BASE, token="mcp-token")
        transport = FakeTransport([])
        with patch("alimail.client.load_credentials", return_value=credentials) as loader:
            client = Client.from_mcp_token(
                "mcp-token", base=APP_BASE, transport=transport, cache=NullCache()
            )
        loader.assert_called_once_with(
            app_id=None,
            app_secret=None,
            base=APP_BASE,
            token="mcp-token",
            email=None,
        )
        self.assertEqual(client.mode, "mcp")
        self.assertEqual(client.token(), "mcp-token")
        self.assertEqual(transport.call_count, 0)

    def test_explicit_token_beats_environment_app_credentials(self):
        # Regression: Client(token=...) used to fall back to the application
        # credentials from ALIMAIL_APP_ID/ALIMAIL_APP_SECRET.
        transport = FakeTransport([json_response(200, {"users": []})])
        env = {"ALIMAIL_APP_ID": "env-id", "ALIMAIL_APP_SECRET": "env-secret"}
        with patch.dict(os.environ, env, clear=True):
            client = Client(
                token="explicit-token",
                base=APP_BASE,
                transport=transport,
                cache=NullCache(),
            )
        self.assertEqual(client.mode, "mcp")
        result = client.get("/v2/users")
        self.assertEqual(result, {"users": []})
        self.assertEqual(transport.calls[0].headers["Authorization"], "Bearer explicit-token")
        self.assertEqual(len(transport.token_calls), 0)

    def test_defaults_are_used_for_retry_settings(self):
        client, _ = make_client()
        self.assertEqual(client.max_retries, DEFAULT_MAX_RETRIES)
        self.assertEqual(client.backoff, DEFAULT_BACKOFF)
        self.assertEqual(client.timeout, DEFAULT_TIMEOUT)
        self.assertTrue(client.verify_ssl)

    def test_negative_max_retries_is_clamped_to_zero(self):
        client, _ = make_client(max_retries=-3)
        self.assertEqual(client.max_retries, 0)

    def test_context_manager_returns_the_client(self):
        client, _ = make_client()
        with client as entered:
            self.assertIs(entered, client)
        client.close()  # idempotent

    def test_resource_groups_are_wired(self):
        client, _ = make_client()
        for name in (
            "users",
            "mail",
            "calendars",
            "organization",
            "domains",
            "departments",
            "groups",
            "contacts",
            "quarantine",
            "message_rules",
            "reports",
            "stream",
        ):
            self.assertIsNotNone(getattr(client, name), name)


class ClientRequestTests(unittest.TestCase):
    def test_get_builds_url_query_and_headers(self):
        client, transport = make_client([json_response(200, {"ok": True})])
        result = client.request(
            "GET",
            "/v2/users",
            params={"size": 5, "filter": "(email=user@example.test)", "cursor": None},
        )
        self.assertEqual(result, {"ok": True})
        call = transport.calls[0]
        self.assertEqual(call.method, "GET")
        self.assertEqual(url_path(call.url), "/v2/users")
        self.assertEqual(
            url_query(call.url),
            {"size": ["5"], "filter": ["(email=user@example.test)"]},
        )
        self.assertEqual(
            call.headers,
            {
                "Authorization": f"Bearer {TOKEN_VALUE}",
                "Accept": "application/json",
            },
        )
        self.assertIsNone(call.json_body)
        self.assertIsNone(call.form)
        self.assertEqual(call.timeout, DEFAULT_TIMEOUT)
        self.assertTrue(call.verify_ssl)

    def test_path_without_leading_slash_is_normalised(self):
        client, transport = make_client([json_response(200, {})])
        client.get("v2/users")
        self.assertEqual(transport.calls[0].url, APP_BASE + "/v2/users")

    def test_custom_headers_are_merged(self):
        client, transport = make_client([json_response(200, {})])
        client.raw(
            "GET",
            "/v2/users",
            headers={"Accept": "text/plain", "X-Trace": "abc"},
        )
        headers = transport.calls[0].headers
        self.assertEqual(headers["Accept"], "text/plain")
        self.assertEqual(headers["X-Trace"], "abc")
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN_VALUE}")

    def test_post_helper_sends_a_json_body(self):
        client, transport = make_client([json_response(200, {"ok": True})])
        result = client.post("/v2/users", json={"name": "张三"})
        self.assertEqual(result, {"ok": True})
        call = transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.json_body, {"name": "张三"})

    def test_form_body_is_forwarded(self):
        client, transport = make_client([json_response(200, {})])
        client.request(
            "POST",
            "/v2/custom/form",
            form={"grant_type": "client_credentials", "client_id": "id"},
        )
        self.assertEqual(
            transport.calls[0].form,
            {"grant_type": "client_credentials", "client_id": "id"},
        )

    def test_raw_bytes_are_forwarded(self):
        client, transport = make_client([json_response(200, {})])
        client.raw("POST", "/v2/stream/session-1", data=b"chunk")
        self.assertEqual(transport.calls[0].data, b"chunk")

    def test_per_call_timeout_overrides_the_client_default(self):
        client, transport = make_client([json_response(200, {})])
        client.raw("GET", "/v2/users", timeout=1.5)
        self.assertEqual(transport.calls[0].timeout, 1.5)

    def test_verify_ssl_is_forwarded(self):
        client, transport = make_client([json_response(200, {})], verify_ssl=False)
        client.raw("GET", "/v2/users")
        self.assertFalse(transport.calls[0].verify_ssl)

    def test_verify_ssl_is_forwarded_to_token_fetch(self):
        transport = FakeTransport(
            [
                json_response(200, {"access_token": "tok", "expires_in": 3600}),
                json_response(200, {"ok": True}),
            ]
        )
        client = Client(
            credentials=Credentials(base=APP_BASE, app_id="a", app_secret="s"),
            transport=transport,
            cache=NullCache(),
            verify_ssl=False,
        )
        client.raw("GET", "/v2/users")
        self.assertEqual(len(transport.calls), 2)
        self.assertFalse(transport.calls[0].verify_ssl)
        self.assertFalse(transport.calls[1].verify_ssl)

    def test_raw_does_not_raise_on_error_status(self):
        client, _ = make_client([json_response(403, {"message": "denied", "detailErrorCode": "x"})])
        response = client.raw("GET", "/v2/users")
        self.assertEqual(response.status, 403)
        self.assertFalse(response.ok)
        self.assertEqual(response.data["message"], "denied")

    def test_token_is_cached_across_requests(self):
        client, transport = make_client(
            [json_response(200, {"a": 1}), json_response(200, {"a": 2})]
        )
        client.get("/v2/users")
        client.get("/v2/domains")
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(len(transport.token_calls), 1)

    def test_mcp_mode_sends_the_personal_token(self):
        client, transport = make_client([json_response(200, {})], auth="mcp", token="mcp-token")
        client.get("/v2/users")
        self.assertEqual(transport.calls[0].headers["Authorization"], "Bearer mcp-token")
        self.assertEqual(len(transport.token_calls), 0)

    def test_mcp_invalidate_token_keeps_the_client_usable(self):
        # Regression: invalidate_token() used to clear the personal token and
        # make the following token()/request raise an AssertionError.
        client, transport = make_client(
            [json_response(200, {"ok": True})], auth="mcp", token="mcp-token"
        )
        client.invalidate_token()
        self.assertEqual(client.token(), "mcp-token")
        result = client.get("/v2/users")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(transport.calls[0].headers["Authorization"], "Bearer mcp-token")

    def test_default_host_token_failure_switches_the_api_base(self):
        transport = FakeTransport(
            [
                TransportError("dns failure"),
                json_response(200, {"access_token": "sg-token", "expires_in": 3600}),
                json_response(200, {"users": []}),
            ]
        )
        client = Client(
            credentials=Credentials(app_id="app-id", app_secret="app-secret"),
            transport=transport,
            cache=NullCache(),
        )
        result = client.get("/v2/users")
        self.assertEqual(result, {"users": []})
        self.assertEqual(client.base, SG_BASE)
        self.assertEqual(transport.urls[0], DEFAULT_BASE + "/oauth2/v2.0/token")
        self.assertEqual(transport.urls[1], SG_BASE + "/oauth2/v2.0/token")
        self.assertTrue(transport.urls[2].startswith(SG_BASE + "/v2/users"))


class ClientErrorMappingTests(unittest.TestCase):
    def test_403_maps_to_permission_denied(self):
        payload = {"message": "no scope", "detailErrorCode": "accessDenied"}
        client, _ = make_client([json_response(403, payload)])
        with self.assertRaises(PermissionDenied) as ctx:
            client.request("GET", "/v2/users")
        error = ctx.exception
        self.assertEqual(error.status, 403)
        self.assertEqual(error.detail_error_code, "accessDenied")
        self.assertEqual(error.message, "no scope")
        self.assertEqual(error.method, "GET")
        self.assertEqual(error.path, "/v2/users")
        self.assertEqual(error.payload, payload)
        self.assertIn("HTTP 403", str(error))
        self.assertIn("GET /v2/users", str(error))

    def test_404_maps_to_not_found(self):
        client, _ = make_client([json_response(404, {"message": "missing"})])
        with self.assertRaises(NotFound) as ctx:
            client.request("GET", "/v2/users/user")
        self.assertEqual(ctx.exception.status, 404)

    def test_401_maps_to_auth_error_in_mcp_mode(self):
        client, transport = make_client(
            [json_response(401, {"message": "token rejected"})], auth="mcp"
        )
        with self.assertRaises(AuthError):
            client.request("GET", "/v2/users")
        self.assertEqual(transport.call_count, 1)

    def test_unknown_status_maps_to_generic_api_error(self):
        client, _ = make_client([json_response(400, {"message": "bad request"})])
        with self.assertRaises(AlimailError) as ctx:
            client.request("GET", "/v2/users")
        self.assertEqual(ctx.exception.status, 400)

    def test_429_maps_to_rate_limit_error(self):
        client, _ = make_client([json_response(429, {"message": "slow down"})], max_retries=0)
        with self.assertRaises(RateLimitError):
            client.request("GET", "/v2/users")

    def test_500_maps_to_server_error_when_retries_are_disabled(self):
        client, _ = make_client([json_response(500, {"message": "boom"})], max_retries=0)
        with self.assertRaises(ServerError):
            client.request("GET", "/v2/users")

    def test_error_payload_without_message_gets_a_default(self):
        client, _ = make_client([json_response(404, None)])
        with self.assertRaises(NotFound) as ctx:
            client.request("GET", "/v2/users")
        self.assertEqual(ctx.exception.message, "request failed")


class ClientRetryTests(unittest.TestCase):
    def test_retry_after_header_is_respected(self):
        client, transport = make_client(
            [
                json_response(429, {"message": "slow"}, {"retry-after": "2.5"}),
                json_response(200, {"ok": True}),
            ]
        )
        with patch("alimail.client.time.sleep") as sleep:
            result = client.request("GET", "/v2/users")
        self.assertEqual(result, {"ok": True})
        sleep.assert_called_once_with(2.5)
        self.assertEqual(transport.call_count, 2)

    def test_invalid_retry_after_falls_back_to_backoff(self):
        client, _ = make_client(
            [
                json_response(429, {"message": "slow"}, {"retry-after": "soon"}),
                json_response(200, {"ok": True}),
            ]
        )
        with patch("alimail.client.time.sleep") as sleep:
            client.request("GET", "/v2/users")
        sleep.assert_called_once_with(DEFAULT_BACKOFF)

    def test_429_backoff_sequence_is_exponential(self):
        client, _ = make_client(
            [
                json_response(429, {}),
                json_response(429, {}),
                json_response(429, {}),
            ]
        )
        with patch("alimail.client.time.sleep") as sleep, self.assertRaises(RateLimitError):
            client.request("GET", "/v2/users")
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [DEFAULT_BACKOFF, DEFAULT_BACKOFF * 2],
        )

    def test_429_is_retried_for_non_idempotent_post(self):
        client, transport = make_client([json_response(429, {}), json_response(200, {"ok": True})])
        with patch("alimail.client.time.sleep"):
            result = client.request("POST", "/v2/users", json={"a": 1})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(transport.call_count, 2)

    def test_custom_backoff_is_used(self):
        client, _ = make_client(
            [json_response(500, {}), json_response(500, {}), json_response(200, {})],
            backoff=0.25,
        )
        with patch("alimail.client.time.sleep") as sleep:
            client.request("GET", "/v2/users")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.25, 0.5])

    def test_5xx_is_retried_for_get(self):
        client, transport = make_client(
            [
                json_response(500, {}),
                json_response(502, {}),
                json_response(200, {"ok": True}),
            ]
        )
        with patch("alimail.client.time.sleep"):
            result = client.request("GET", "/v2/users")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(transport.call_count, 3)

    def test_5xx_is_not_retried_for_post(self):
        client, transport = make_client([json_response(500, {"message": "boom"})])
        with patch("alimail.client.time.sleep") as sleep, self.assertRaises(ServerError):
            client.request("POST", "/v2/users", json={"a": 1})
        self.assertEqual(transport.call_count, 1)
        sleep.assert_not_called()

    def test_transport_error_is_not_retried_for_post(self):
        client, transport = make_client([TransportError("connection reset")])
        with patch("alimail.client.time.sleep") as sleep, self.assertRaises(TransportError):
            client.request("POST", "/v2/messages", json={"message": {}})
        self.assertEqual(transport.call_count, 1)
        sleep.assert_not_called()

    def test_transport_error_is_retried_for_get(self):
        client, transport = make_client(
            [
                TransportError("first"),
                TransportError("second"),
                json_response(200, {"ok": True}),
            ]
        )
        with patch("alimail.client.time.sleep") as sleep:
            result = client.request("GET", "/v2/users")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(transport.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [DEFAULT_BACKOFF, DEFAULT_BACKOFF * 2],
        )

    def test_transport_error_retries_are_bounded(self):
        client, transport = make_client(
            [
                TransportError("first"),
                TransportError("second"),
                TransportError("third"),
            ]
        )
        with patch("alimail.client.time.sleep"), self.assertRaises(TransportError):
            client.request("GET", "/v2/users")
        self.assertEqual(transport.call_count, 3)

    def test_non_transport_exceptions_are_not_retried(self):
        client, transport = make_client([ValueError("programming error")])
        with patch("alimail.client.time.sleep") as sleep, self.assertRaises(ValueError):
            client.request("GET", "/v2/users")
        self.assertEqual(transport.call_count, 1)
        sleep.assert_not_called()

    def test_zero_retries_disables_transport_retries(self):
        client, transport = make_client([TransportError("boom")], max_retries=0)
        with self.assertRaises(TransportError):
            client.request("GET", "/v2/users")
        self.assertEqual(transport.call_count, 1)

    def test_401_refreshes_the_token_and_retries_once(self):
        client, transport = make_client(
            [
                json_response(401, {"message": "expired"}),
                json_response(200, {"ok": True}),
            ]
        )
        with patch("alimail.client.time.sleep") as sleep:
            result = client.request("GET", "/v2/users")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(len(transport.token_calls), 2)
        sleep.assert_not_called()

    def test_401_is_only_retried_once(self):
        client, transport = make_client(
            [
                json_response(401, {"message": "expired"}),
                json_response(401, {"message": "still expired"}),
            ]
        )
        with self.assertRaises(AuthError):
            client.request("GET", "/v2/users")
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(len(transport.token_calls), 2)

    def test_401_is_retried_for_post_too(self):
        client, transport = make_client(
            [
                json_response(401, {"message": "expired"}),
                json_response(200, {"ok": True}),
            ]
        )
        with patch("alimail.client.time.sleep"):
            result = client.request("POST", "/v2/users", json={"a": 1})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(transport.call_count, 2)

    def test_mcp_mode_never_refreshes_on_401(self):
        client, transport = make_client([json_response(401, {"message": "expired"})], auth="mcp")
        with self.assertRaises(AuthError):
            client.request("GET", "/v2/users")
        self.assertEqual(transport.call_count, 1)


class ClientPaginationTests(unittest.TestCase):
    def test_follows_next_cursor_until_empty(self):
        client, transport = make_client(
            [
                json_response(200, {"users": [{"id": "1"}], "nextCursor": "c1"}),
                json_response(200, {"users": [{"id": "2"}], "nextCursor": "c2"}),
                json_response(200, {"users": [{"id": "3"}], "nextCursor": ""}),
            ]
        )
        items = list(client.paginate("GET", "/v2/users", item_key="users", params={"size": 2}))
        self.assertEqual([item["id"] for item in items], ["1", "2", "3"])
        self.assertEqual(transport.call_count, 3)
        self.assertEqual(url_query(transport.calls[0].url), {"size": ["2"]})
        self.assertEqual(url_query(transport.calls[1].url), {"size": ["2"], "cursor": ["c1"]})
        self.assertEqual(url_query(transport.calls[2].url), {"size": ["2"], "cursor": ["c2"]})

    def test_stops_on_missing_cursor(self):
        client, transport = make_client([json_response(200, {"users": [{"id": "1"}]})])
        items = list(client.paginate("GET", "/v2/users", item_key="users"))
        self.assertEqual(items, [{"id": "1"}])
        self.assertEqual(transport.call_count, 1)

    def test_stops_on_repeated_cursor(self):
        client, transport = make_client(
            [
                json_response(200, {"users": [{"id": "1"}], "nextCursor": "same"}),
                json_response(200, {"users": [{"id": "2"}], "nextCursor": "same"}),
            ]
        )
        items = list(client.paginate("GET", "/v2/users", item_key="users"))
        self.assertEqual([item["id"] for item in items], ["1", "2"])
        self.assertEqual(transport.call_count, 2)

    def test_custom_cursor_key(self):
        client, _ = make_client(
            [
                json_response(200, {"rows": [{"id": "1"}], "cursor": "next"}),
                json_response(200, {"rows": [{"id": "2"}], "cursor": None}),
            ]
        )
        items = list(client.paginate("GET", "/v2/rows", item_key="rows", cursor_key="cursor"))
        self.assertEqual([item["id"] for item in items], ["1", "2"])

    def test_item_key_none_uses_the_first_list_value(self):
        client, _ = make_client(
            [json_response(200, {"meta": {"total": 1}, "rows": [{"id": "1"}], "nextCursor": ""})]
        )
        items = list(client.paginate("GET", "/v2/rows"))
        self.assertEqual(items, [{"id": "1"}])

    def test_plain_list_payload_is_supported(self):
        client, _ = make_client([json_response(200, [{"id": "1"}, {"id": "2"}])])
        items = list(client.paginate("GET", "/v2/rows"))
        self.assertEqual([item["id"] for item in items], ["1", "2"])

    def test_max_pages_limits_the_number_of_requests(self):
        client, transport = make_client(
            [
                json_response(200, {"users": [{"id": "1"}], "nextCursor": "c1"}),
                json_response(200, {"users": [{"id": "2"}], "nextCursor": "c2"}),
                json_response(200, {"users": [{"id": "3"}], "nextCursor": ""}),
            ]
        )
        items = list(client.paginate("GET", "/v2/users", item_key="users", max_pages=2))
        self.assertEqual([item["id"] for item in items], ["1", "2"])
        self.assertEqual(transport.call_count, 2)

    def test_generator_is_lazy(self):
        client, transport = make_client([json_response(200, {"users": [], "nextCursor": ""})])
        stream = client.paginate("GET", "/v2/users", item_key="users")
        self.assertEqual(transport.call_count, 0)
        list(stream)
        self.assertEqual(transport.call_count, 1)


class ClientCallTests(unittest.TestCase):
    def test_path_mapping_fills_placeholders(self):
        client, transport = make_client([json_response(200, {"departments": []})])
        client.call("list_sub_departments", path={"id": "dept/1"}, query={"limit": 10})
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), "/v2/departments/dept%2F1/departments")
        self.assertEqual(url_query(call.url), {"limit": ["10"]})

    def test_path_parameters_can_be_keyword_arguments(self):
        client, transport = make_client([json_response(200, {"messages": []})])
        client.call(
            "list_messages",
            email="user@example.test",
            folderId="2",
            size=5,
        )
        call = transport.calls[0]
        self.assertEqual(
            url_path(call.url),
            "/v2/users/user%40example.test/mailFolders/2/messages",
        )
        self.assertEqual(url_query(call.url), {"size": ["5"]})

    def test_root_placeholder_is_kept_raw(self):
        client, transport = make_client([json_response(200, {})])
        client.call("list_sub_departments", path={"id": "$root"})
        self.assertEqual(url_path(transport.calls[0].url), "/v2/departments/$root/departments")

    def test_query_mapping_and_keyword_arguments_are_merged(self):
        client, transport = make_client([json_response(200, {})])
        client.call("list_users", query={"size": 10}, filter="(email=*)")
        self.assertEqual(
            url_query(transport.calls[0].url),
            {"size": ["10"], "filter": ["(email=*)"]},
        )

    def test_none_query_values_are_dropped(self):
        client, transport = make_client([json_response(200, {})])
        client.call("list_users", size=None, cursor="")
        call = transport.calls[0]
        query = url_query(call.url)
        self.assertNotIn("size", query)
        self.assertEqual(query, {"cursor": [""]})
        self.assertEqual(url_path(call.url), "/v2/users")

    def test_json_body_is_sent(self):
        client, transport = make_client([json_response(200, {})])
        client.call(
            "send_message",
            path={"email": "user@example.test", "id": "m-1"},
            json={"email": "user@example.test", "id": "m-1"},
        )
        call = transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(url_path(call.url), "/v2/users/user%40example.test/messages/m-1/send")
        self.assertEqual(call.json_body, {"email": "user@example.test", "id": "m-1"})

    def test_unknown_operation_raises_key_error(self):
        client, transport = make_client([])
        with self.assertRaises(KeyError):
            client.call("definitely_not_an_operation")
        self.assertEqual(transport.call_count, 0)

    def test_missing_path_parameter_raises_key_error(self):
        client, transport = make_client([])
        with self.assertRaises(KeyError) as ctx:
            client.call("get_department")
        self.assertIn("requires path parameters", str(ctx.exception))
        self.assertEqual(transport.call_count, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
