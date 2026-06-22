import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model.chatInfo import ChatInfo
from source.whatsappSource import WhatsAppSource

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'waha', 'group_messages.json')


def load_fixture():
    with open(FIXTURE, encoding='utf-8') as f:
        return json.load(f)


class TestExtractSenderName(unittest.TestCase):
    def test_uses_pushname_from_gows_info(self):
        named = next(m for m in load_fixture()
                     if (m.get('_data') or {}).get('Info', {}).get('PushName'))
        self.assertEqual(WhatsAppSource._extract_sender_name(named), 'Tanita')

    def test_falls_back_to_sender_number_when_no_pushname(self):
        unnamed = next(m for m in load_fixture()
                       if not (m.get('_data') or {}).get('Info', {}).get('PushName'))
        result = WhatsAppSource._extract_sender_name(unnamed)
        self.assertTrue(result)
        self.assertNotIn('@', result)
        self.assertTrue(result.isdigit())

    def test_never_returns_legacy_empty_for_real_payload(self):
        # Old code read msg['sender']['pushName'] which does not exist in GOWS
        for m in load_fixture():
            self.assertNotEqual(WhatsAppSource._extract_sender_name(m), '')


class TestGroupTitleResolution(unittest.TestCase):
    """GOWS /groups/{id} returns the group name under key `Name` (capital N),
    not `subject`/`name`. Regression: blank chat_title in reports."""

    def _make_source(self, group_info):
        src = WhatsAppSource(
            waha_url="http://x", waha_api_key="k", session_name="s",
            target_label="Madrid", timezone_name="Europe/Madrid", db_service=None,
        )
        group_id = "120363246895560676@g.us"

        def fake_request(method, path, **kwargs):
            if path.endswith('/labels'):
                return [{"id": "4", "name": "Madrid"}]
            if path.endswith('/labels/4/chats'):
                return [{"id": group_id}]
            if path.endswith(f'/groups/{group_id}'):
                return group_info
            raise AssertionError(f"unexpected path {path}")

        src._request = fake_request
        return src, group_id

    def test_resolves_group_name_from_gows_Name_key(self):
        src, _ = self._make_source({"JID": "x", "Name": "Спроси Мадрид! 2"})
        chats = asyncio.run(src.get_target_chats())
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0].chat_title, "Спроси Мадрид! 2")

    def test_falls_back_to_chat_id_when_no_name(self):
        src, group_id = self._make_source({"JID": "x"})
        chats = asyncio.run(src.get_target_chats())
        self.assertEqual(chats[0].chat_title, group_id)
        self.assertNotEqual(chats[0].chat_title, "")


class _FakeDB:
    """Minimal db_service stub returning a fixed cursor."""
    def __init__(self, last_id=None, last_ts=None):
        self._last_id = last_id
        self._last_ts = last_ts

    def get_last_processed_timestamp(self, dialog_id):
        return self._last_ts

    def get_last_processed_message(self, dialog_id):
        return self._last_id


class TestBoundaryExclusion(unittest.TestCase):
    """WAHA filter.timestamp.gte is inclusive, so the cursor message comes back
    every run. Regression: same WhatsApp message reported every hour."""

    def _make_source(self, db, messages):
        src = WhatsAppSource(
            waha_url="http://x", waha_api_key="k", session_name="s",
            target_label="Madrid", timezone_name="Europe/Madrid", db_service=db,
        )
        src._request = lambda method, path, **kwargs: messages
        return src

    def _recent(self, msg_id):
        now = int(datetime.now(timezone.utc).timestamp())
        return {"id": msg_id, "body": "meetup tonight", "timestamp": now, "type": "chat"}

    def test_skips_cursor_boundary_message(self):
        msgs = [self._recent("AAA"), self._recent("BBB")]
        src = self._make_source(_FakeDB(last_id="AAA", last_ts=datetime.now(timezone.utc)), msgs)
        chat = ChatInfo(source="whatsapp", chat_id="g@g.us", chat_title="Madrid")
        result = asyncio.run(src.fetch_messages(chat))
        ids = [m.message_id for m in result]
        self.assertIn("BBB", ids)
        self.assertNotIn("AAA", ids)

    def test_keeps_all_when_no_cursor(self):
        msgs = [self._recent("AAA"), self._recent("BBB")]
        src = self._make_source(_FakeDB(last_id=None, last_ts=None), msgs)
        chat = ChatInfo(source="whatsapp", chat_id="g@g.us", chat_title="Madrid")
        ids = [m.message_id for m in asyncio.run(src.fetch_messages(chat))]
        self.assertEqual(sorted(ids), ["AAA", "BBB"])


if __name__ == '__main__':
    unittest.main()
