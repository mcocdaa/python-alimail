"""Tests for the operation registry (:mod:`alimail.operations`)."""

from __future__ import annotations

import re
import unittest

from alimail.operations import (
    Operation,
    all_operations,
    get_operation,
    iter_operations,
    load_raw,
)

OPERATION_COUNT = 112
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class OperationRegistryTests(unittest.TestCase):
    def test_registry_contains_112_operations(self):
        self.assertEqual(len(all_operations()), OPERATION_COUNT)
        self.assertEqual(len(load_raw()), OPERATION_COUNT)

    def test_operation_names_are_unique_and_sorted(self):
        names = [operation.name for operation in all_operations()]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names, sorted(names))

    def test_operation_ids_are_unique(self):
        ids = [operation.operation_id for operation in all_operations()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ids))

    def test_every_operation_metadata_is_valid(self):
        for operation in all_operations():
            with self.subTest(operation=operation.name):
                self.assertRegex(operation.name, NAME_PATTERN)
                self.assertIn(operation.method, {"GET", "POST", "DELETE", "PATCH", "PUT"})
                self.assertTrue(operation.path.startswith("/v2/"))
                self.assertTrue(operation.summary)
                self.assertIsInstance(operation.tags, tuple)
                self.assertTrue(operation.tags)
                self.assertIsInstance(operation.scopes, tuple)
                self.assertIsInstance(operation.params, tuple)

    def test_path_placeholders_match_documented_path_parameters(self):
        for operation in all_operations():
            with self.subTest(operation=operation.name):
                documented = {
                    param["name"] for param in operation.params if param.get("in") == "path"
                }
                self.assertEqual(set(operation.path_params), documented)
                self.assertEqual(len(operation.path_params), len(set(operation.path_params)))

    def test_build_path_works_for_every_operation(self):
        for operation in all_operations():
            with self.subTest(operation=operation.name):
                values = dict.fromkeys(operation.path_params, "value/with space")
                path = operation.build_path(values)
                self.assertTrue(path.startswith("/v2/"))
                self.assertNotIn("{", path)

    def test_describe_renders_metadata(self):
        operation = get_operation("list_users")
        text = operation.describe()
        self.assertIn("list_users", text)
        self.assertIn("GET", text)
        self.assertIn("/v2/users", text)
        self.assertIn(operation.summary, text)


class GetOperationTests(unittest.TestCase):
    def test_lookup_by_friendly_name(self):
        operation = get_operation("list_users")
        self.assertIsInstance(operation, Operation)
        self.assertEqual(operation.name, "list_users")
        self.assertEqual(operation.method, "GET")
        self.assertEqual(operation.path, "/v2/users")

    def test_lookup_by_operation_id(self):
        operation = get_operation("alimailpb_ud_UserService_ListUsers")
        self.assertEqual(operation.name, "list_users")

    def test_lookup_by_operation_id_is_case_insensitive(self):
        operation = get_operation("ALIMAILPB_UD_USERSERVICE_LISTUSERS")
        self.assertEqual(operation.name, "list_users")

    def test_lookup_by_name_is_case_insensitive(self):
        self.assertEqual(get_operation("LIST_USERS").name, "list_users")

    def test_substring_does_not_match_arbitrary_operation(self):
        for needle in ("delete", "send"):
            with self.subTest(needle=needle), self.assertRaises(KeyError):
                get_operation(needle)

    def test_unknown_operation_suggests_close_matches(self):
        with self.assertRaises(KeyError) as ctx:
            get_operation("list_user")
        message = str(ctx.exception)
        self.assertIn("Unknown operation", message)
        self.assertIn("list_users", message)

    def test_unknown_operation_raises_key_error(self):
        with self.assertRaises(KeyError) as ctx:
            get_operation("definitely_not_an_operation")
        self.assertIn("Unknown operation", str(ctx.exception))
        self.assertIn("ops list", str(ctx.exception))

    def test_iter_operations_without_tag_returns_everything(self):
        self.assertEqual(list(iter_operations()), list(all_operations()))

    def test_iter_operations_filters_by_tag(self):
        operations = list(iter_operations("用户"))
        self.assertTrue(operations)
        self.assertLess(len(operations), OPERATION_COUNT)
        for operation in operations:
            self.assertIn("用户", operation.tags)

    def test_iter_operations_unknown_tag_is_empty(self):
        self.assertEqual(list(iter_operations("no-such-tag")), [])


class BuildPathTests(unittest.TestCase):
    def test_fills_a_single_placeholder(self):
        operation = get_operation("get_department")
        self.assertEqual(operation.path_params, ("id",))
        self.assertEqual(operation.build_path({"id": "dept/1"}), "/v2/departments/dept%2F1")

    def test_encodes_email_and_folder_placeholders(self):
        operation = get_operation("list_messages")
        path = operation.build_path({"email": "user@example.test", "folderId": "folder 2"})
        self.assertEqual(
            path,
            "/v2/users/user%40example.test/mailFolders/folder%202/messages",
        )

    def test_keeps_dollar_root_untouched(self):
        operation = get_operation("list_sub_departments")
        self.assertEqual(
            operation.build_path({"id": "$root"}),
            "/v2/departments/$root/departments",
        )

    def test_missing_placeholder_raises_key_error(self):
        operation = get_operation("send_message")
        with self.assertRaises(KeyError) as ctx:
            operation.build_path({"email": "user@example.test"})
        message = str(ctx.exception)
        self.assertIn("requires path parameters", message)
        self.assertIn("id", message)

    def test_stringifies_non_string_values(self):
        operation = get_operation("get_department")
        self.assertEqual(operation.build_path({"id": 123}), "/v2/departments/123")

    def test_extra_values_are_ignored(self):
        operation = get_operation("get_department")
        self.assertEqual(
            operation.build_path({"id": "d1", "unused": "x"}),
            "/v2/departments/d1",
        )

    def test_no_placeholders_means_no_required_values(self):
        operation = get_operation("list_users")
        self.assertEqual(operation.path_params, ())
        self.assertEqual(operation.build_path({}), "/v2/users")

    def test_operations_are_immutable(self):
        operation = get_operation("list_users")
        with self.assertRaises(AttributeError):
            operation.name = "renamed"  # type: ignore[misc]


class PublicApiTests(unittest.TestCase):
    def test_package_exports(self):
        import alimail

        for name in alimail.__all__:
            self.assertTrue(hasattr(alimail, name), name)

    def test_package_version(self):
        import alimail

        self.assertEqual(alimail.__version__, "0.1.0")

    def test_public_helpers_are_re_exported(self):
        import alimail

        self.assertIs(alimail.get_operation, get_operation)
        self.assertIs(alimail.all_operations, all_operations)
        self.assertIs(alimail.Operation, Operation)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
