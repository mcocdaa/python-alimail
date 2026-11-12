"""Tests for credential discovery and cache paths (:mod:`alimail.config`)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from alimail.config import (
    CREDS_FILENAME,
    DEFAULT_BASE,
    SG_BASE,
    Credentials,
    load_credentials,
    token_cache_path,
)
from alimail.errors import AlimailError, ConfigError
from tests.fakes import temp_directory


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ConfigTestCase(unittest.TestCase):
    """Shared temp cwd/home and a cleansed ``os.environ``."""

    def setUp(self) -> None:
        self._tmp = temp_directory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.cwd = self.root / "project"
        self.home = self.root / "home"
        self.cwd.mkdir()
        self.home.mkdir()
        env_patch = patch.dict(os.environ, {}, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def load(self, **kwargs: object) -> Credentials:
        kwargs.setdefault("cwd", self.cwd)
        kwargs.setdefault("home", self.home)
        kwargs.setdefault("env", {})
        return load_credentials(**kwargs)  # type: ignore[arg-type]


class LoadCredentialsEnvironmentTests(ConfigTestCase):
    def test_explicit_arguments_win_over_environment(self):
        creds = self.load(
            app_id="explicit-id",
            app_secret="explicit-secret",
            env={"ALIMAIL_APP_ID": "env-id", "ALIMAIL_APP_SECRET": "env-secret"},
        )
        self.assertEqual(creds.mode, "app")
        self.assertEqual(creds.app_id, "explicit-id")
        self.assertEqual(creds.app_secret, "explicit-secret")
        self.assertEqual(creds.base, DEFAULT_BASE)
        self.assertEqual(creds.source, "arguments/env")

    def test_app_credentials_from_environment(self):
        creds = self.load(env={"ALIMAIL_APP_ID": "env-id", "ALIMAIL_APP_SECRET": "env-secret"})
        self.assertEqual(creds.mode, "app")
        self.assertEqual(creds.app_id, "env-id")
        self.assertEqual(creds.app_secret, "env-secret")
        self.assertTrue(creds.base_is_default)

    def test_base_from_environment_is_trimmed(self):
        creds = self.load(
            env={
                "ALIMAIL_APP_ID": "env-id",
                "ALIMAIL_APP_SECRET": "env-secret",
                "ALIMAIL_BASE": "https://api.example.test/",
            }
        )
        self.assertEqual(creds.base, "https://api.example.test")
        self.assertFalse(creds.base_is_default)

    def test_mcp_token_and_email_from_environment(self):
        creds = self.load(
            env={
                "ALIMAIL_MCP_TOKEN": "mcp-token",
                "ALIMAIL_EMAIL": "user@example.test",
            }
        )
        self.assertEqual(creds.mode, "mcp")
        self.assertEqual(creds.token, "mcp-token")
        self.assertEqual(creds.email, "user@example.test")
        self.assertEqual(creds.base, DEFAULT_BASE)
        self.assertEqual(creds.source, "arguments/env")

    def test_explicit_token_wins_over_environment_token(self):
        creds = self.load(token="explicit-token", env={"ALIMAIL_MCP_TOKEN": "env-token"})
        self.assertEqual(creds.mode, "mcp")
        self.assertEqual(creds.token, "explicit-token")

    def test_environment_app_credentials_beat_mcp_token(self):
        creds = self.load(
            env={
                "ALIMAIL_APP_ID": "env-id",
                "ALIMAIL_APP_SECRET": "env-secret",
                "ALIMAIL_MCP_TOKEN": "mcp-token",
            }
        )
        self.assertEqual(creds.mode, "app")

    def test_explicit_token_beats_environment_app_credentials(self):
        # Regression: a caller-supplied token used to be ignored whenever the
        # environment also carried an application id/secret pair.
        creds = self.load(
            token="explicit-token",
            env={"ALIMAIL_APP_ID": "env-id", "ALIMAIL_APP_SECRET": "env-secret"},
        )
        self.assertEqual(creds.mode, "mcp")
        self.assertEqual(creds.token, "explicit-token")
        self.assertEqual(creds.base, DEFAULT_BASE)
        self.assertEqual(creds.source, "arguments/env")

    def test_explicit_app_credentials_beat_environment_token(self):
        creds = self.load(
            app_id="explicit-id",
            app_secret="explicit-secret",
            env={"ALIMAIL_MCP_TOKEN": "env-token"},
        )
        self.assertEqual(creds.mode, "app")
        self.assertEqual(creds.app_id, "explicit-id")


class LoadCredentialsFileTests(ConfigTestCase):
    def test_project_local_credentials_file(self):
        local = _write_json(
            self.cwd / CREDS_FILENAME,
            {
                "app_id": "local-id",
                "app_secret": "local-secret",
                "base": "https://local.example.test/",
            },
        )
        creds = self.load()
        self.assertEqual(creds.mode, "app")
        self.assertEqual(creds.app_id, "local-id")
        self.assertEqual(creds.app_secret, "local-secret")
        self.assertEqual(creds.base, "https://local.example.test")
        self.assertEqual(creds.source, str(local))

    def test_project_local_file_token_variant(self):
        local = _write_json(
            self.cwd / CREDS_FILENAME,
            {"token": "local-token", "email": "local@example.test"},
        )
        creds = self.load()
        self.assertEqual(creds.mode, "mcp")
        self.assertEqual(creds.token, "local-token")
        self.assertEqual(creds.email, "local@example.test")
        self.assertEqual(creds.source, str(local))

    def test_local_file_token_beats_app_pair_inside_the_same_file(self):
        _write_json(
            self.cwd / CREDS_FILENAME,
            {"app_id": "a", "app_secret": "b", "token": "t"},
        )
        creds = self.load()
        self.assertEqual(creds.mode, "mcp")
        self.assertEqual(creds.token, "t")

    def test_environment_credentials_beat_project_local_file(self):
        _write_json(
            self.cwd / CREDS_FILENAME,
            {"app_id": "local-id", "app_secret": "local-secret"},
        )
        creds = self.load(env={"ALIMAIL_APP_ID": "env-id", "ALIMAIL_APP_SECRET": "env-secret"})
        self.assertEqual(creds.app_id, "env-id")

    def test_user_credentials_file_is_used_when_no_local_file(self):
        user_file = _write_json(
            self.home / ".alimail" / "creds.json",
            {"app_id": "user-id", "app_secret": "user-secret"},
        )
        creds = self.load()
        self.assertEqual(creds.app_id, "user-id")
        self.assertEqual(creds.source, str(user_file))

    def test_project_local_file_beats_user_credentials_file(self):
        _write_json(
            self.cwd / CREDS_FILENAME,
            {"app_id": "local-id", "app_secret": "local-secret"},
        )
        _write_json(
            self.home / ".alimail" / "creds.json",
            {"app_id": "user-id", "app_secret": "user-secret"},
        )
        creds = self.load()
        self.assertEqual(creds.app_id, "local-id")

    def test_explicit_base_overrides_file_base(self):
        _write_json(
            self.cwd / CREDS_FILENAME,
            {"app_id": "a", "app_secret": "b", "base": "https://file.example.test"},
        )
        creds = self.load(base="https://explicit.example.test")
        self.assertEqual(creds.base, "https://explicit.example.test")

    def test_malformed_local_file_is_ignored(self):
        (self.cwd / CREDS_FILENAME).write_text("not-json{", encoding="utf-8")
        user_file = _write_json(
            self.home / ".alimail" / "creds.json",
            {"app_id": "user-id", "app_secret": "user-secret"},
        )
        creds = self.load()
        self.assertEqual(creds.source, str(user_file))

    def test_local_file_without_credentials_is_ignored(self):
        _write_json(self.cwd / CREDS_FILENAME, {"base": "https://x.example.test"})
        with self.assertRaises(ConfigError):
            self.load()


class LoadCredentialsAccountsTests(ConfigTestCase):
    def test_accounts_file_from_appdata(self):
        appdata = self.root / "appdata"
        accounts = _write_json(
            appdata / "Alimail" / "accounts.json",
            {
                "accounts": [
                    {
                        "email": "user@example.test",
                        "token": "appdata-token",
                        "baseUrl": "https://mcp.example.test/",
                    }
                ]
            },
        )
        with patch.dict(os.environ, {"APPDATA": str(appdata)}, clear=True):
            creds = self.load()
        self.assertEqual(creds.mode, "mcp")
        self.assertEqual(creds.token, "appdata-token")
        self.assertEqual(creds.email, "user@example.test")
        self.assertEqual(creds.base, "https://mcp.example.test")
        self.assertEqual(creds.source, str(accounts))

    def test_accounts_file_falls_back_to_home_directory(self):
        accounts = _write_json(
            self.home / ".alimail" / "accounts.json",
            {"accounts": [{"email": "home@example.test", "token": "home-token"}]},
        )
        creds = self.load()
        self.assertEqual(creds.token, "home-token")
        self.assertEqual(creds.base, DEFAULT_BASE)
        self.assertEqual(creds.source, str(accounts))

    def test_appdata_accounts_file_beats_home_accounts_file(self):
        appdata = self.root / "appdata"
        _write_json(
            appdata / "Alimail" / "accounts.json",
            {"accounts": [{"email": "a@example.test", "token": "appdata-token"}]},
        )
        _write_json(
            self.home / ".alimail" / "accounts.json",
            {"accounts": [{"email": "h@example.test", "token": "home-token"}]},
        )
        with patch.dict(os.environ, {"APPDATA": str(appdata)}, clear=True):
            creds = self.load()
        self.assertEqual(creds.token, "appdata-token")

    def test_account_selection_by_email_is_case_insensitive(self):
        _write_json(
            self.home / ".alimail" / "accounts.json",
            {
                "accounts": [
                    {"email": "first@example.test", "token": "first-token"},
                    {"email": "Second@Example.Test", "token": "second-token"},
                ]
            },
        )
        creds = self.load(email="second@example.test")
        self.assertEqual(creds.token, "second-token")
        self.assertEqual(creds.email, "Second@Example.Test")

    def test_first_account_is_used_without_an_email_hint(self):
        _write_json(
            self.home / ".alimail" / "accounts.json",
            {
                "accounts": [
                    {"email": "first@example.test", "token": "first-token"},
                    {"email": "second@example.test", "token": "second-token"},
                ]
            },
        )
        creds = self.load()
        self.assertEqual(creds.token, "first-token")
        self.assertEqual(creds.email, "first@example.test")

    def test_unknown_email_falls_back_to_the_first_account(self):
        _write_json(
            self.home / ".alimail" / "accounts.json",
            {"accounts": [{"email": "first@example.test", "token": "first-token"}]},
        )
        creds = self.load(email="nobody@example.test")
        self.assertEqual(creds.token, "first-token")

    def test_explicit_base_overrides_account_base_url(self):
        _write_json(
            self.home / ".alimail" / "accounts.json",
            {
                "accounts": [
                    {
                        "email": "user@example.test",
                        "token": "mcp-token",
                        "baseUrl": "https://file.example.test",
                    }
                ]
            },
        )
        creds = self.load(base="https://explicit.example.test")
        self.assertEqual(creds.base, "https://explicit.example.test")
        self.assertEqual(creds.token, "mcp-token")

    def test_accounts_without_tokens_are_ignored(self):
        _write_json(
            self.home / ".alimail" / "accounts.json",
            {"accounts": [{"email": "user@example.test"}]},
        )
        with self.assertRaises(ConfigError):
            self.load()

    def test_empty_accounts_list_is_ignored(self):
        _write_json(self.home / ".alimail" / "accounts.json", {"accounts": []})
        with self.assertRaises(ConfigError):
            self.load()

    def test_accounts_payload_that_is_not_a_mapping_is_ignored(self):
        _write_json(self.home / ".alimail" / "accounts.json", ["not", "accounts"])
        with self.assertRaises(ConfigError):
            self.load()


class LoadCredentialsFailureTests(ConfigTestCase):
    def test_missing_credentials_raise_config_error_with_hint(self):
        with self.assertRaises(ConfigError) as ctx:
            self.load()
        message = str(ctx.exception)
        self.assertIn("ALIMAIL_APP_ID", message)
        self.assertIn("ALIMAIL_MCP_TOKEN", message)
        self.assertIn("accounts.json", message)

    def test_config_error_is_an_alimail_error(self):
        self.assertTrue(issubclass(ConfigError, AlimailError))

    def test_no_network_or_real_credentials_are_touched(self):
        # Resolving credentials only reads the injected temp cwd/home; the
        # failure proves nothing outside the sandbox was consulted.
        with (
            patch("alimail.config._read_json", return_value=None) as reader,
            self.assertRaises(ConfigError),
        ):
            self.load()
        paths = {str(call.args[0]) for call in reader.call_args_list}
        self.assertTrue(paths)
        self.assertTrue(all(path.startswith(str(self.root)) for path in paths))


class CredentialsModelTests(unittest.TestCase):
    def test_default_credentials_have_no_mode(self):
        creds = Credentials()
        self.assertEqual(creds.mode, "none")
        self.assertEqual(creds.base, DEFAULT_BASE)
        self.assertTrue(creds.base_is_default)

    def test_app_credentials_mode(self):
        creds = Credentials(app_id="id", app_secret="secret")
        self.assertEqual(creds.mode, "app")

    def test_token_credentials_mode(self):
        creds = Credentials(token="token")
        self.assertEqual(creds.mode, "mcp")

    def test_custom_base_is_not_default(self):
        creds = Credentials(base=SG_BASE)
        self.assertFalse(creds.base_is_default)
        self.assertEqual(creds.mode, "none")

    def test_configuration_constants(self):
        self.assertEqual(DEFAULT_BASE, "https://alimail-cn.aliyuncs.com")
        self.assertEqual(SG_BASE, "https://alimail-sg.aliyuncs.com")
        self.assertEqual(CREDS_FILENAME, "alimail_creds.json")


class TokenCachePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_directory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"

    def _with_platform(self, name: str):
        return patch("alimail.config.os", SimpleNamespace(name=name))

    def test_windows_uses_localappdata(self):
        local = self.root / "localappdata"
        with self._with_platform("nt"):
            path = token_cache_path(env={"LOCALAPPDATA": str(local)}, home=self.home)
        self.assertEqual(path, local / "alimail" / "token-cache.json")

    def test_windows_without_localappdata_uses_xdg_cache_home(self):
        cache = self.root / "xdg"
        with self._with_platform("nt"):
            path = token_cache_path(env={"XDG_CACHE_HOME": str(cache)}, home=self.home)
        self.assertEqual(path, cache / "alimail" / "token-cache.json")

    def test_windows_without_any_env_uses_home_cache(self):
        with self._with_platform("nt"):
            path = token_cache_path(env={}, home=self.home)
        self.assertEqual(path, self.home / ".cache" / "alimail" / "token-cache.json")

    def test_posix_ignores_localappdata(self):
        cache = self.root / "xdg"
        with self._with_platform("posix"):
            path = token_cache_path(
                env={
                    "LOCALAPPDATA": str(self.root / "localappdata"),
                    "XDG_CACHE_HOME": str(cache),
                },
                home=self.home,
            )
        self.assertEqual(path, cache / "alimail" / "token-cache.json")

    def test_posix_default_cache_location(self):
        with self._with_platform("posix"):
            path = token_cache_path(env={}, home=self.home)
        self.assertEqual(path, self.home / ".cache" / "alimail" / "token-cache.json")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
