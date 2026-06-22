"""Tests for the Source reference seam (CONTEXT.md): each source adapter owns
its own calendar-event locator via get_event_reference, and MessageService
assembles the Event description through that one seam."""

import os
import sys
import types
import unittest
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model.unifiedMessage import UnifiedMessage
from source.telegramSource import TelegramSource
from source.whatsappSource import WhatsAppSource
from service.messageService import MessageService


def _msg(source="telegram", chat_title="Madrid Ru", raw=None):
    return UnifiedMessage(
        source=source,
        chat_id="123",
        chat_title=chat_title,
        message_id="m1",
        text="meetup tonight",
        timestamp=datetime(2026, 6, 22, 18, 0, tzinfo=timezone.utc),
        sender_name="Tanita",
        raw=raw,
    )


class TestTelegramEventReference(unittest.TestCase):
    def _source(self):
        return TelegramSource(client=None, env=None, db_service=None)

    def test_no_raw_returns_empty(self):
        self.assertEqual(self._source().get_event_reference(_msg(raw=None)), "")

    def test_public_channel_link(self):
        chat = types.SimpleNamespace(has_link=True, username="madrid_ru", id=999)
        raw = types.SimpleNamespace(chat=chat, id=55)
        self.assertEqual(
            self._source().get_event_reference(_msg(raw=raw)),
            "https://t.me/madrid_ru/55",
        )

    def test_private_channel_c_link(self):
        chat = types.SimpleNamespace(has_link=False, username=None, id=999)
        raw = types.SimpleNamespace(chat=chat, id=7)
        self.assertEqual(
            self._source().get_event_reference(_msg(raw=raw)),
            "https://t.me/c/999/7",
        )


class TestWhatsAppEventReference(unittest.TestCase):
    def test_tag_from_chat_title(self):
        src = WhatsAppSource(
            waha_url="http://x", waha_api_key="k", session_name="s",
            target_label="L", timezone_name="Europe/Madrid", db_service=None,
        )
        self.assertEqual(
            src.get_event_reference(_msg(source="whatsapp", chat_title="Madrid Ru")),
            "[WhatsApp] Madrid Ru",
        )


class _FakeSource:
    def __init__(self, ref):
        self._ref = ref

    def get_event_reference(self, message):
        return self._ref


class _FakeCalendar:
    def __init__(self):
        self.last_description = None

    def create_event(self, name, description, start_datetime, end_datetime):
        self.last_description = description
        return {"id": "g1"}


class _FakeDB:
    def get_events_starting_around(self, start, window_minutes=120):
        return []  # never a duplicate

    def store_calendar_event(self, **kwargs):
        pass


class TestEventDescriptionAssembly(unittest.IsolatedAsyncioTestCase):
    def _service(self, calendar):
        return MessageService(
            client=None, db_service=_FakeDB(), text_analyzer=None,
            calendar_service=calendar, env=None,
        )

    def _event(self):
        return {
            "title": "Meetup",
            "description": "Come hang out",
            "start_datetime": "2026-06-22T20:00:00",
            "end_datetime": "2026-06-22T22:00:00",
            "message_id": "m1",
        }

    async def test_reference_appended_with_blank_line(self):
        cal = _FakeCalendar()
        await self._service(cal)._process_single_event(
            self._event(), _msg(), _FakeSource("https://t.me/x/1"),
            "telegram:123", "Madrid Ru",
        )
        self.assertEqual(cal.last_description, "Come hang out\n\nhttps://t.me/x/1")

    async def test_empty_reference_leaves_description_untouched(self):
        cal = _FakeCalendar()
        await self._service(cal)._process_single_event(
            self._event(), _msg(), _FakeSource(""),
            "telegram:123", "Madrid Ru",
        )
        self.assertEqual(cal.last_description, "Come hang out")

    async def test_none_source_does_not_raise(self):
        cal = _FakeCalendar()
        await self._service(cal)._process_single_event(
            self._event(), _msg(), None, "telegram:123", "Madrid Ru",
        )
        self.assertEqual(cal.last_description, "Come hang out")


if __name__ == "__main__":
    unittest.main()
