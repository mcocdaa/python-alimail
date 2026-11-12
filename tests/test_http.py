"""Tests for the standard-library HTTP transport (:mod:`alimail._http`)."""

from __future__ import annotations

import gzip
import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from alimail import _http
from alimail.errors import AlimailError, TransportError


def _fake_urlopen(
    payload: bytes = b"{}",
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a context-manager shaped stand-in for ``urlopen()``'s return value."""
    response = MagicMock()
    response.read.return_value = payload
    response.status = status
    response.headers = dict(headers or {"content-type": "application/json"})
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class BuildUrlTests(unittest.TestCase):
    def test_joins_base_and_path(self):
        self.assertEqual(
            _http.build_url("https://api.example.test", "/v2/users"),
            "https://api.example.test/v2/users",
        )

    def test_strips_trailing_slash_from_base(self):
        self.assertEqual(
            _http.build_url("https://api.example.test/", "/v2/users"),
            "https://api.example.test/v2/users",
        )

    def test_adds_leading_slash_to_path(self):
        self.assertEqual(
            _http.build_url("https://api.example.test", "v2/users"),
            "https://api.example.test/v2/users",
        )

    def test_encodes_query_parameters(self):
        url = _http.build_url(
            "https://api.example.test",
            "/v2/users",
            {"size": 5, "filter": "(email=user@example.test)", "$select": "id,name"},
        )
        self.assertEqual(
            url,
            "https://api.example.test/v2/users"
            "?size=5&filter=%28email%3Duser%40example.test%29&%24select=id%2Cname",
        )

    def test_drops_none_parameters(self):
        url = _http.build_url("https://api.example.test", "/v2/users", {"size": 5, "cursor": None})
        self.assertEqual(url, "https://api.example.test/v2/users?size=5")

    def test_skips_question_mark_when_all_params_are_none(self):
        url = _http.build_url(
            "https://api.example.test", "/v2/users", {"size": None, "cursor": None}
        )
        self.assertEqual(url, "https://api.example.test/v2/users")

    def test_keeps_empty_string_values(self):
        url = _http.build_url("https://api.example.test", "/v2/users", {"cursor": ""})
        self.assertEqual(url, "https://api.example.test/v2/users?cursor=")

    def test_appends_to_existing_query_string(self):
        url = _http.build_url("https://api.example.test", "/v2/users?a=1", {"b": 2})
        # A path that already carries a query string is joined with "&".
        self.assertEqual(url, "https://api.example.test/v2/users?a=1&b=2")

    def test_serialises_sequences_with_doseq(self):
        url = _http.build_url("https://api.example.test", "/v2/users", {"ids": ["a", "b"]})
        self.assertEqual(url, "https://api.example.test/v2/users?ids=a&ids=b")

    def test_empty_params_mapping_is_ignored(self):
        self.assertEqual(
            _http.build_url("https://api.example.test", "/v2/users", {}),
            "https://api.example.test/v2/users",
        )


class RequestBodyTests(unittest.TestCase):
    @patch("alimail._http.urllib.request.urlopen")
    def test_json_body_is_serialised(self, urlopen):
        urlopen.return_value = _fake_urlopen(payload=b'{"ok": true}')
        _http.request(
            "POST",
            "https://api.example.test/v2/users",
            json_body={"name": "张三", "size": 5},
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.data,
            json.dumps({"name": "张三", "size": 5}, ensure_ascii=False).encode("utf-8"),
        )
        self.assertEqual(request.get_header("Content-type"), "application/json")

    @patch("alimail._http.urllib.request.urlopen")
    def test_form_body_is_urlencoded(self, urlopen):
        urlopen.return_value = _fake_urlopen()
        _http.request(
            "POST",
            "https://api.example.test/oauth2/v2.0/token",
            form={"grant_type": "client_credentials", "client_id": "id"},
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.data, b"grant_type=client_credentials&client_id=id")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")

    @patch("alimail._http.urllib.request.urlopen")
    def test_raw_bytes_body_is_forwarded(self, urlopen):
        urlopen.return_value = _fake_urlopen()
        _http.request("POST", "https://api.example.test/v2/stream/1", data=b"chunk")
        self.assertEqual(urlopen.call_args.args[0].data, b"chunk")

    @patch("alimail._http.urllib.request.urlopen")
    def test_default_headers_and_user_agent(self, urlopen):
        urlopen.return_value = _fake_urlopen()
        _http.request("GET", "https://api.example.test/v2/users")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("User-agent"), _http.USER_AGENT)

    @patch("alimail._http.urllib.request.urlopen")
    def test_custom_headers_override_defaults(self, urlopen):
        urlopen.return_value = _fake_urlopen()
        _http.request(
            "GET",
            "https://api.example.test/v2/users",
            headers={"Accept": "text/plain", "X-Trace": "abc"},
            user_agent="custom-agent",
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "text/plain")
        self.assertEqual(request.get_header("X-trace"), "abc")
        self.assertEqual(request.get_header("User-agent"), "custom-agent")

    @patch("alimail._http.urllib.request.urlopen")
    def test_method_is_upper_cased(self, urlopen):
        urlopen.return_value = _fake_urlopen()
        _http.request("get", "https://api.example.test/v2/users")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")

    @patch("alimail._http.urllib.request.urlopen")
    def test_timeout_is_forwarded(self, urlopen):
        urlopen.return_value = _fake_urlopen()
        _http.request("GET", "https://api.example.test/v2/users", timeout=7.5)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7.5)

    @patch("alimail._http.urllib.request.urlopen")
    def test_ssl_verification_is_enabled_by_default(self, urlopen):
        urlopen.return_value = _fake_urlopen()
        _http.request("GET", "https://api.example.test/v2/users")
        self.assertIsNone(urlopen.call_args.kwargs["context"])

    @patch("alimail._http.ssl._create_unverified_context", return_value="insecure")
    @patch("alimail._http.urllib.request.urlopen")
    def test_ssl_verification_can_be_disabled(self, urlopen, unverified):
        urlopen.return_value = _fake_urlopen()
        _http.request("GET", "https://api.example.test/v2/users", verify_ssl=False)
        unverified.assert_called_once_with()
        self.assertEqual(urlopen.call_args.kwargs["context"], "insecure")


class ResponseDecodingTests(unittest.TestCase):
    @patch("alimail._http.urllib.request.urlopen")
    def test_decodes_json_payload(self, urlopen):
        urlopen.return_value = _fake_urlopen(
            payload=b'{"users": [], "total": 0}',
            headers={"content-type": "application/json"},
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.data, {"users": [], "total": 0})
        self.assertTrue(response.ok)

    @patch("alimail._http.urllib.request.urlopen")
    def test_decodes_gzip_json_payload(self, urlopen):
        payload = gzip.compress(b'{"ok": true}')
        urlopen.return_value = _fake_urlopen(
            payload=payload,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.data, {"ok": True})

    @patch("alimail._http.urllib.request.urlopen")
    def test_sniffs_json_without_content_type(self, urlopen):
        urlopen.return_value = _fake_urlopen(
            payload=b'{"ok": true}', headers={"content-type": "text/plain"}
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.data, {"ok": True})

    @patch("alimail._http.urllib.request.urlopen")
    def test_sniffs_json_list_payload(self, urlopen):
        urlopen.return_value = _fake_urlopen(
            payload=b"[1, 2]", headers={"content-type": "text/plain"}
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.data, [1, 2])

    @patch("alimail._http.urllib.request.urlopen")
    def test_returns_plain_text_for_non_json(self, urlopen):
        urlopen.return_value = _fake_urlopen(
            payload=b"hello", headers={"content-type": "text/plain"}
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.data, "hello")

    @patch("alimail._http.urllib.request.urlopen")
    def test_returns_text_when_json_is_malformed(self, urlopen):
        urlopen.return_value = _fake_urlopen(
            payload=b"{not json", headers={"content-type": "application/json"}
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.data, "{not json")

    @patch("alimail._http.urllib.request.urlopen")
    def test_empty_body_decodes_to_none(self, urlopen):
        urlopen.return_value = _fake_urlopen(payload=b"", headers={})
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertIsNone(response.data)

    @patch("alimail._http.urllib.request.urlopen")
    def test_response_headers_are_lower_cased(self, urlopen):
        urlopen.return_value = _fake_urlopen(
            payload=b"{}", headers={"Content-Type": "application/json", "X-Req-Id": "m1"}
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertEqual(response.headers["x-req-id"], "m1")

    def test_raw_response_ok_property(self):
        self.assertTrue(_http.RawResponse(200, {}).ok)
        self.assertTrue(_http.RawResponse(204, None).ok)
        self.assertFalse(_http.RawResponse(400, {}).ok)
        self.assertFalse(_http.RawResponse(500, {}).ok)


class ErrorHandlingTests(unittest.TestCase):
    @patch("alimail._http.urllib.request.urlopen")
    def test_http_error_status_is_returned_not_raised(self, urlopen):
        error = urllib.error.HTTPError(
            "https://api.example.test/v2/users",
            404,
            "Not Found",
            {"content-type": "application/json"},
            io.BytesIO(b'{"message": "missing", "detailErrorCode": "notFound"}'),
        )
        urlopen.side_effect = error
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.status, 404)
        self.assertFalse(response.ok)
        self.assertEqual(response.data["detailErrorCode"], "notFound")
        self.assertEqual(response.headers["content-type"], "application/json")

    @patch("alimail._http.urllib.request.urlopen")
    def test_http_error_without_body_returns_none(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.example.test/v2/users", 500, "Boom", {}, io.BytesIO(b"")
        )
        response = _http.request("GET", "https://api.example.test/v2/users")
        self.assertEqual(response.status, 500)
        self.assertIsNone(response.data)

    @patch("alimail._http.urllib.request.urlopen")
    def test_connection_error_becomes_transport_error(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(TransportError) as ctx:
            _http.request("GET", "https://api.example.test/v2/users")
        self.assertIn("GET https://api.example.test/v2/users failed", str(ctx.exception))
        self.assertIn("connection refused", str(ctx.exception))

    @patch("alimail._http.urllib.request.urlopen")
    def test_os_error_becomes_transport_error(self, urlopen):
        urlopen.side_effect = OSError("socket closed")
        with self.assertRaises(TransportError):
            _http.request("GET", "https://api.example.test/v2/users")

    @patch("alimail._http.urllib.request.urlopen")
    def test_timeout_becomes_transport_error(self, urlopen):
        urlopen.side_effect = TimeoutError("timed out")
        with self.assertRaises(TransportError):
            _http.request("GET", "https://api.example.test/v2/users")

    def test_transport_error_is_an_alimail_error(self):
        self.assertTrue(issubclass(TransportError, AlimailError))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
