"""Tests for the resource groups under :mod:`alimail.resources`."""

from __future__ import annotations

import unittest

from alimail.resources import q, recipients
from tests.fakes import json_response, make_client, url_path, url_query

EMAIL = "user@example.test"
ENCODED_EMAIL = "user%40example.test"
USER_ROOT = f"/v2/users/{ENCODED_EMAIL}"


class ResourceTestCase(unittest.TestCase):
    def new_client(self, responses=None, **kwargs):
        return make_client(responses, **kwargs)


class UsersResourceTests(ResourceTestCase):
    def test_list_uses_size_not_limit(self):
        client, transport = self.new_client([json_response(200, {"users": []})])
        client.users.list(
            size=10,
            filter="(email=*)",
            cursor="c1",
            orderby="email",
            order="asc",
            select="id,email",
        )
        call = transport.calls[0]
        self.assertEqual(call.method, "GET")
        self.assertEqual(url_path(call.url), "/v2/users")
        self.assertEqual(
            url_query(call.url),
            {
                "size": ["10"],
                "filter": ["(email=*)"],
                "cursor": ["c1"],
                "orderby": ["email"],
                "order": ["asc"],
                "$select": ["id,email"],
            },
        )
        self.assertNotIn("limit", url_query(call.url))

    def test_list_without_arguments_has_no_query_string(self):
        client, transport = self.new_client()
        client.users.list()
        self.assertEqual(transport.calls[0].url, client.base + "/v2/users")
        self.assertEqual(url_query(transport.calls[0].url), {})

    def test_get_encodes_the_identifier(self):
        client, transport = self.new_client()
        client.users.get(EMAIL, select="id,email")
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"/v2/users/{ENCODED_EMAIL}")
        self.assertEqual(url_query(call.url), {"$select": ["id,email"]})

    def test_shared_with_me_path(self):
        client, transport = self.new_client()
        client.users.shared_with_me(EMAIL)
        self.assertEqual(url_path(transport.calls[0].url), f"{USER_ROOT}/sharedWithMe")

    def test_shared_members_path(self):
        client, transport = self.new_client()
        client.users.shared_members(EMAIL)
        self.assertEqual(url_path(transport.calls[0].url), f"{USER_ROOT}/sharedMembers")

    def test_mailbox_settings_query(self):
        client, transport = self.new_client()
        client.users.mailbox_settings(EMAIL, select="timeZone")
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/mailboxSettings")
        self.assertEqual(url_query(call.url), {"$select": ["timeZone"]})

    def test_iter_all_follows_the_cursor(self):
        client, transport = self.new_client(
            [
                json_response(200, {"users": [{"id": "1"}], "nextCursor": "c1"}),
                json_response(200, {"users": [{"id": "2"}], "nextCursor": ""}),
            ]
        )
        items = list(client.users.iter_all(size=50, filter="(email=*)"))
        self.assertEqual([item["id"] for item in items], ["1", "2"])
        self.assertEqual(
            url_query(transport.calls[0].url),
            {"size": ["50"], "filter": ["(email=*)"]},
        )
        self.assertEqual(
            url_query(transport.calls[1].url),
            {"size": ["50"], "filter": ["(email=*)"], "cursor": ["c1"]},
        )


class MailFolderTests(ResourceTestCase):
    def test_folders_path_encodes_the_email(self):
        client, transport = self.new_client()
        client.mail.folders(EMAIL)
        call = transport.calls[0]
        self.assertEqual(call.method, "GET")
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/mailFolders")
        self.assertNotIn("?", call.url)

    def test_inbox_uses_folder_id_2(self):
        client, transport = self.new_client([json_response(200, {"messages": []})])
        client.mail.inbox(EMAIL)
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/mailFolders/2/messages")
        query = url_query(call.url)
        self.assertEqual(query["size"], ["20"])
        self.assertEqual(query["$select"], ["subject,from,receivedDateTime,isRead,id"])

    def test_inbox_custom_size(self):
        client, transport = self.new_client()
        client.mail.inbox(EMAIL, size=5)
        self.assertEqual(url_query(transport.calls[0].url)["size"], ["5"])

    def test_find_folder_id_by_display_name(self):
        client, _ = self.new_client(
            [
                json_response(
                    200,
                    {
                        "folders": [
                            {"id": "10", "displayName": "收件箱"},
                            {"id": "11", "displayName": "SentItems"},
                        ]
                    },
                )
            ]
        )
        self.assertEqual(client.mail.find_folder_id(EMAIL, "inbox"), "10")

    def test_find_folder_id_is_case_insensitive(self):
        client, _ = self.new_client(
            [json_response(200, {"folders": [{"id": "99", "displayName": "INBOX"}]})]
        )
        self.assertEqual(client.mail.find_folder_id(EMAIL, "inbox"), "99")

    def test_find_folder_id_supports_chinese_aliases(self):
        client, _ = self.new_client(
            [json_response(200, {"folders": [{"id": "77", "displayName": "草稿箱"}]})]
        )
        self.assertEqual(client.mail.find_folder_id(EMAIL, "draft"), "77")

    def test_find_folder_id_falls_back_to_builtin_ids(self):
        client, transport = self.new_client([json_response(200, {"folders": []})])
        expected = {
            "inbox": "2",
            "sent": "1",
            "spam": "3",
            "draft": "5",
            "deleted": "6",
            "custom": "custom",
        }
        for name, folder_id in expected.items():
            self.assertEqual(client.mail.find_folder_id(EMAIL, name), folder_id)
        self.assertEqual(transport.call_count, len(expected))

    def test_messages_default_folder_and_select(self):
        client, transport = self.new_client()
        client.mail.messages(EMAIL)
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/mailFolders/2/messages")
        query = url_query(call.url)
        self.assertNotIn("size", query)
        self.assertNotIn("orderby", query)
        self.assertEqual(query["$select"], ["subject,from,receivedDateTime,isRead,id"])

    def test_messages_custom_folder_and_filters(self):
        client, transport = self.new_client()
        client.mail.messages(
            EMAIL,
            folder_id="5",
            size=5,
            cursor="c1",
            select=None,
            orderby="receivedDateTime desc",
        )
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/mailFolders/5/messages")
        self.assertEqual(
            url_query(call.url),
            {
                "size": ["5"],
                "cursor": ["c1"],
                "orderby": ["receivedDateTime desc"],
            },
        )

    def test_message_encodes_the_message_id(self):
        client, transport = self.new_client()
        client.mail.message(EMAIL, "m/1")
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/messages/m%2F1")
        self.assertEqual(url_query(call.url), {})

    def test_message_select_parameter(self):
        client, transport = self.new_client()
        client.mail.message(EMAIL, "m-1", select="subject")
        self.assertEqual(url_query(transport.calls[0].url), {"$select": ["subject"]})

    def test_attachments_path(self):
        client, transport = self.new_client()
        client.mail.attachments(EMAIL, "m-1")
        self.assertEqual(url_path(transport.calls[0].url), f"{USER_ROOT}/messages/m-1/attachments")


class MailSearchAndMutationTests(ResourceTestCase):
    def test_search_body(self):
        client, transport = self.new_client([json_response(200, {"messages": []})])
        client.mail.search(EMAIL, "subject:hello")
        call = transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/messages/query")
        self.assertEqual(
            call.json_body,
            {
                "email": EMAIL,
                "query": "subject:hello",
                "cursor": "",
                "size": 20,
            },
        )

    def test_search_custom_size_and_cursor(self):
        client, transport = self.new_client()
        client.mail.search(EMAIL, "from:a@example.test", size=5, cursor="c1")
        self.assertEqual(
            transport.calls[0].json_body,
            {
                "email": EMAIL,
                "query": "from:a@example.test",
                "cursor": "c1",
                "size": 5,
            },
        )

    def test_delete_body(self):
        client, transport = self.new_client()
        client.mail.delete(EMAIL, ("1", "2"))
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/messages/batchDelete")
        self.assertEqual(call.json_body, {"email": EMAIL, "ids": ["1", "2"]})

    def test_delete_with_type(self):
        client, transport = self.new_client()
        client.mail.delete(EMAIL, ["1"], delete_type="HARD_DELETE")
        self.assertEqual(
            transport.calls[0].json_body,
            {"email": EMAIL, "ids": ["1"], "deleteType": "HARD_DELETE"},
        )

    def test_move_body(self):
        client, transport = self.new_client()
        client.mail.move(EMAIL, ["1", "2"], "5")
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/messages/move")
        self.assertEqual(
            call.json_body,
            {
                "email": EMAIL,
                "ids": ["1", "2"],
                "destinationFolderId": "5",
            },
        )

    def test_mark_read_and_unread_actions(self):
        client, transport = self.new_client([json_response(200, {}), json_response(200, {})])
        client.mail.mark_read(EMAIL, ["1"])
        client.mail.mark_read(EMAIL, ["1"], read=False)
        self.assertEqual(transport.calls[0].json_body["action"], "markRead")
        self.assertEqual(transport.calls[1].json_body["action"], "markUnread")
        self.assertEqual(url_path(transport.calls[0].url), f"{USER_ROOT}/messages/batchUpdate")


class MailDraftAndSendTests(ResourceTestCase):
    def test_create_draft_body_shape(self):
        client, transport = self.new_client([json_response(200, {"message": {"id": "m"}})])
        client.mail.create_draft(
            EMAIL,
            to=["a@example.test", "b@example.test"],
            subject="Hello",
            text="plain text",
            html="<p>html</p>",
            cc=["cc@example.test"],
            bcc=["bcc@example.test"],
        )
        call = transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/messages")
        self.assertEqual(
            call.json_body,
            {
                "message": {
                    "subject": "Hello",
                    "from": {"email": EMAIL},
                    "toRecipients": [
                        {"email": "a@example.test"},
                        {"email": "b@example.test"},
                    ],
                    "body": {"bodyText": "plain text", "bodyHtml": "<p>html</p>"},
                    "ccRecipients": [{"email": "cc@example.test"}],
                    "bccRecipients": [{"email": "bcc@example.test"}],
                }
            },
        )

    def test_create_draft_minimal_body(self):
        client, transport = self.new_client()
        client.mail.create_draft(EMAIL, to="only@example.test", subject="Hi")
        message = transport.calls[0].json_body["message"]
        self.assertEqual(message["toRecipients"], [{"email": "only@example.test"}])
        self.assertEqual(message["body"], {})
        self.assertNotIn("ccRecipients", message)
        self.assertNotIn("bccRecipients", message)

    def test_create_draft_sender_override(self):
        client, transport = self.new_client()
        client.mail.create_draft(
            EMAIL, to="x@example.test", subject="Hi", sender="robot@example.test"
        )
        self.assertEqual(
            transport.calls[0].json_body["message"]["from"]["email"],
            "robot@example.test",
        )

    def test_create_draft_accepts_recipient_mappings(self):
        client, transport = self.new_client()
        client.mail.create_draft(EMAIL, to=[{"email": "a@example.test", "name": "A"}], subject="Hi")
        self.assertEqual(
            transport.calls[0].json_body["message"]["toRecipients"],
            [{"email": "a@example.test", "name": "A"}],
        )

    def test_send_is_a_two_step_flow(self):
        draft = {"message": {"id": "msg-1", "subject": "Hi"}}
        client, transport = self.new_client(
            [json_response(200, draft), json_response(200, {"sent": True})]
        )
        result = client.mail.send(EMAIL, to="to@example.test", subject="Hi", text="body")
        self.assertEqual(len(transport.calls), 2)
        first, second = transport.calls
        self.assertEqual(first.method, "POST")
        self.assertEqual(url_path(first.url), f"{USER_ROOT}/messages")
        self.assertEqual(first.json_body["message"]["subject"], "Hi")
        self.assertEqual(second.method, "POST")
        self.assertEqual(url_path(second.url), f"{USER_ROOT}/messages/msg-1/send")
        self.assertEqual(
            second.json_body,
            {"email": EMAIL, "id": "msg-1", "saveToSentItems": True},
        )
        self.assertEqual(result, {"draft": draft, "send": {"sent": True}})

    def test_send_without_saving_to_sent_items(self):
        client, transport = self.new_client(
            [
                json_response(200, {"message": {"id": "msg-1"}}),
                json_response(200, {}),
            ]
        )
        client.mail.send(EMAIL, to="x@example.test", subject="Hi", save_to_sent=False)
        self.assertFalse(transport.calls[1].json_body["saveToSentItems"])

    def test_send_accepts_a_top_level_draft_id(self):
        client, transport = self.new_client(
            [json_response(200, {"id": "raw-id"}), json_response(200, {})]
        )
        client.mail.send(EMAIL, to="x@example.test", subject="Hi")
        self.assertEqual(url_path(transport.calls[1].url), f"{USER_ROOT}/messages/raw-id/send")
        self.assertEqual(transport.calls[1].json_body["id"], "raw-id")

    def test_send_without_draft_id_raises_value_error(self):
        client, transport = self.new_client([json_response(200, {})])
        with self.assertRaises(ValueError) as ctx:
            client.mail.send(EMAIL, to="x@example.test", subject="Hi")
        self.assertIn("does not contain a message id", str(ctx.exception))
        self.assertEqual(transport.call_count, 1)


class CalendarsResourceTests(ResourceTestCase):
    def test_list_and_get(self):
        client, transport = self.new_client([json_response(200, {}), json_response(200, {})])
        client.calendars.list(EMAIL)
        client.calendars.get(EMAIL, "cal/1")
        self.assertEqual(url_path(transport.calls[0].url), f"{USER_ROOT}/calendars")
        self.assertEqual(url_path(transport.calls[1].url), f"{USER_ROOT}/calendars/cal%2F1")

    def test_events_query_parameters(self):
        client, transport = self.new_client()
        client.calendars.events(
            EMAIL,
            "cal-1",
            start="2026-01-01T00:00:00Z",
            end="2026-01-02T00:00:00Z",
            size=10,
            cursor="c1",
        )
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/calendars/cal-1/eventsview")
        self.assertEqual(
            url_query(call.url),
            {
                "start": ["2026-01-01T00:00:00Z"],
                "end": ["2026-01-02T00:00:00Z"],
                "size": ["10"],
                "cursor": ["c1"],
            },
        )

    def test_get_event_encodes_ids(self):
        client, transport = self.new_client()
        client.calendars.get_event(EMAIL, "cal 1", "ev/2")
        self.assertEqual(
            url_path(transport.calls[0].url),
            f"{USER_ROOT}/calendars/cal%201/events/ev%2F2",
        )

    def test_create_event_sends_json(self):
        client, transport = self.new_client()
        client.calendars.create_event(EMAIL, "cal-1", {"subject": "Standup"})
        call = transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.json_body, {"subject": "Standup"})
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/calendars/cal-1/events")

    def test_delete_event_uses_delete_method(self):
        client, transport = self.new_client()
        client.calendars.delete_event(EMAIL, "cal-1", "ev-1")
        self.assertEqual(transport.calls[0].method, "DELETE")
        self.assertEqual(
            url_path(transport.calls[0].url),
            f"{USER_ROOT}/calendars/cal-1/events/ev-1",
        )

    def test_schedule_sends_payload(self):
        client, transport = self.new_client()
        payload = {"schedules": ["user@example.test"]}
        client.calendars.schedule(EMAIL, payload)
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/calendars/getSchedule")
        self.assertEqual(call.json_body, payload)


class DirectoryResourceTests(ResourceTestCase):
    def test_organization_get_keeps_dollar_current(self):
        client, transport = self.new_client()
        client.organization.get()
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), "/v2/organization/$current")
        self.assertNotIn("%24", call.url)

    def test_organization_update_uses_patch(self):
        client, transport = self.new_client()
        client.organization.update({"name": "Org"})
        call = transport.calls[0]
        self.assertEqual(call.method, "PATCH")
        self.assertEqual(call.json_body, {"name": "Org"})

    def test_domains_endpoints(self):
        client, transport = self.new_client([json_response(200, {}) for _ in range(5)])
        client.domains.list()
        client.domains.get("example.test")
        client.domains.create({"domain": "new.example.test"})
        client.domains.verify("example.test")
        client.domains.delete("example.test")
        calls = transport.calls
        self.assertEqual(url_path(calls[0].url), "/v2/domains")
        self.assertEqual(url_path(calls[1].url), "/v2/domains/example.test")
        self.assertEqual(calls[2].method, "POST")
        self.assertEqual(calls[2].json_body, {"domain": "new.example.test"})
        self.assertEqual(url_path(calls[3].url), "/v2/domains/example.test/verify")
        self.assertEqual(calls[4].method, "DELETE")

    def test_departments_children_defaults_to_root(self):
        client, transport = self.new_client()
        client.departments.children()
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), "/v2/departments/$root/departments")
        self.assertNotIn("?", call.url)

    def test_departments_children_and_users_with_query(self):
        client, transport = self.new_client()
        client.departments.children("$root", size=10)
        client.departments.users("d/1", size=5, select="id,email")
        self.assertEqual(url_query(transport.calls[0].url), {"size": ["10"]})
        self.assertEqual(url_path(transport.calls[1].url), "/v2/departments/d%2F1/users")
        self.assertEqual(
            url_query(transport.calls[1].url),
            {"size": ["5"], "$select": ["id,email"]},
        )

    def test_departments_get_chain_and_create(self):
        client, transport = self.new_client()
        client.departments.get("d-1")
        client.departments.chain("d-1")
        client.departments.create({"name": "Eng"})
        self.assertEqual(url_path(transport.calls[0].url), "/v2/departments/d-1")
        self.assertEqual(url_path(transport.calls[1].url), "/v2/departments/d-1/chain")
        self.assertEqual(transport.calls[2].method, "POST")
        self.assertEqual(transport.calls[2].json_body, {"name": "Eng"})

    def test_groups_endpoints(self):
        client, transport = self.new_client()
        client.groups.list(size=10, cursor="c1")
        client.groups.get("group@example.test")
        client.groups.members("group-1", size=5)
        self.assertEqual(
            url_query(transport.calls[0].url),
            {"size": ["10"], "cursor": ["c1"]},
        )
        self.assertEqual(url_path(transport.calls[1].url), "/v2/groups/group%40example.test")
        self.assertEqual(url_path(transport.calls[2].url), "/v2/groups/group-1/members")
        self.assertEqual(url_query(transport.calls[2].url), {"size": ["5"]})

    def test_contacts_endpoints(self):
        client, transport = self.new_client()
        client.contacts.get_folder("f-1")
        client.contacts.folders()
        client.contacts.child_folders("$root")
        client.contacts.contacts("f-1", size=5)
        client.contacts.get_contact("c/1")
        calls = transport.calls
        self.assertEqual(url_path(calls[0].url), "/v2/sharedContactFolders/f-1")
        self.assertEqual(url_path(calls[1].url), "/v2/sharedContactFolders/$root/childFolders")
        self.assertEqual(url_path(calls[2].url), "/v2/sharedContactFolders/$root/childFolders")
        self.assertEqual(url_path(calls[3].url), "/v2/sharedContactFolders/f-1/contacts")
        self.assertEqual(url_query(calls[3].url), {"size": ["5"]})
        self.assertEqual(url_path(calls[4].url), "/v2/sharedContacts/c%2F1")


class SecurityAndStreamResourceTests(ResourceTestCase):
    def test_quarantine_search_passes_parameters(self):
        client, transport = self.new_client()
        client.quarantine.search(EMAIL, from_="a@example.test", size=5)
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/quarantine/messages/search")
        self.assertEqual(
            url_query(call.url),
            {"from_": ["a@example.test"], "size": ["5"]},
        )

    def test_quarantine_get_and_attachments(self):
        client, transport = self.new_client()
        client.quarantine.get(EMAIL, "q/1")
        client.quarantine.attachments(EMAIL, "q-1")
        self.assertEqual(
            url_path(transport.calls[0].url),
            f"{USER_ROOT}/quarantine/messages/q%2F1",
        )
        self.assertEqual(
            url_path(transport.calls[1].url),
            f"{USER_ROOT}/quarantine/messages/q-1/attachments",
        )

    def test_quarantine_release_sends_payload(self):
        client, transport = self.new_client()
        client.quarantine.release(EMAIL, "q-1", {"comment": "safe"})
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), f"{USER_ROOT}/quarantine/messages/q-1/release")
        self.assertEqual(call.json_body, {"comment": "safe"})

    def test_quarantine_release_defaults_to_empty_payload(self):
        client, transport = self.new_client()
        client.quarantine.release(EMAIL, "q-1")
        self.assertEqual(transport.calls[0].json_body, {})

    def test_message_rules_allow_block_lists(self):
        client, transport = self.new_client()
        client.message_rules.allow_block_lists()
        self.assertEqual(url_path(transport.calls[0].url), "/v2/messageRules/allowBlockLists")
        self.assertNotIn("?", transport.calls[0].url)

    def test_message_rules_forward_parameters(self):
        client, transport = self.new_client()
        client.message_rules.allow_block_lists(size=5)
        self.assertEqual(url_query(transport.calls[0].url), {"size": ["5"]})

    def test_reports_search_body(self):
        client, transport = self.new_client()
        client.reports.search(start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z", size=1)
        call = transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(url_path(call.url), "/v2/reports")
        self.assertEqual(
            call.json_body,
            {
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": "2026-01-02T00:00:00Z",
                "size": 1,
            },
        )

    def test_stream_upload_forwards_bytes_and_content_type(self):
        client, transport = self.new_client()
        client.stream.upload("session-1", b"chunk")
        call = transport.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(url_path(call.url), "/v2/stream/session-1")
        self.assertEqual(call.data, b"chunk")
        self.assertEqual(call.headers["Content-Type"], "application/octet-stream")

    def test_stream_upload_custom_content_type(self):
        client, transport = self.new_client()
        client.stream.upload("session 1", b"x", content_type="text/plain")
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), "/v2/stream/session%201")
        self.assertEqual(call.headers["Content-Type"], "text/plain")


class ResourceHelpersTests(unittest.TestCase):
    def test_q_encodes_path_segments(self):
        self.assertEqual(q(EMAIL), ENCODED_EMAIL)
        self.assertEqual(q("a/b"), "a%2Fb")
        self.assertEqual(q("a b"), "a%20b")

    def test_q_keeps_dollar_placeholders_raw(self):
        self.assertEqual(q("$root"), "$root")
        self.assertEqual(q("$current"), "$current")

    def test_q_stringifies_values(self):
        self.assertEqual(q(123), "123")

    def test_recipients_normalisation(self):
        self.assertEqual(recipients(None), [])
        self.assertEqual(recipients("a@example.test"), [{"email": "a@example.test"}])
        self.assertEqual(
            recipients(["a@example.test", "b@example.test"]),
            [{"email": "a@example.test"}, {"email": "b@example.test"}],
        )

    def test_recipients_copies_mappings(self):
        source = [{"email": "a@example.test", "name": "A"}]
        result = recipients(source)
        self.assertEqual(result, source)
        self.assertIsNot(result[0], source[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
