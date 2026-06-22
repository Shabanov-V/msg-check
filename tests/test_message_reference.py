import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model.unifiedMessage import UnifiedMessage
from service.util import Util, MAX_MESSAGE_LEN
from source.whatsappSource import WhatsAppSource


def _wa_source():
    return WhatsAppSource(
        waha_url="http://x", waha_api_key="k", session_name="s",
        target_label="Madrid", timezone_name="Europe/Madrid", db_service=None,
    )


def _msg(**kw):
    base = dict(
        source="whatsapp", chat_id="c@g.us", chat_title="Madrid Group",
        message_id="1", text="hello", timestamp=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),
        sender_name="Ann",
    )
    base.update(kw)
    return UnifiedMessage(**base)


class TestWhatsAppLocator(unittest.TestCase):
    def test_locator_line_present(self):
        ref = _wa_source().get_message_reference(_msg(chat_title="Madrid Group"))
        self.assertIn("📍 [WhatsApp] Madrid Group", ref)


class TestMediaPlaceholder(unittest.TestCase):
    def test_media_only_shows_label(self):
        ref = _wa_source().get_message_reference(_msg(text="", media_type="photo"))
        self.assertIn("🖼 Photo", ref)

    def test_media_with_caption_shows_both(self):
        ref = _wa_source().get_message_reference(_msg(text="look", media_type="video"))
        self.assertIn("🎬 Video", ref)
        self.assertIn("look", ref)

    def test_plain_text_has_no_label(self):
        ref = _wa_source().get_message_reference(_msg(text="just text", media_type=None))
        self.assertNotIn("Photo", ref)
        self.assertIn("just text", ref)

    def test_detect_media_mapping(self):
        self.assertEqual(WhatsAppSource._detect_media({"type": "image"}), "photo")
        self.assertEqual(WhatsAppSource._detect_media({"type": "ptt"}), "audio")
        self.assertIsNone(WhatsAppSource._detect_media({"type": "chat"}))


class TestTruncateHtml(unittest.TestCase):
    def test_short_unchanged(self):
        s = "<b>hi</b>"
        self.assertEqual(Util.truncate_html(s, 100), s)

    def test_respects_max_len(self):
        s = "x" * 5000
        out = Util.truncate_html(s, MAX_MESSAGE_LEN)
        self.assertLessEqual(len(out), MAX_MESSAGE_LEN)
        self.assertIn("[truncated]", out)

    def test_balances_open_tag(self):
        s = "<b>" + "x" * 5000 + "</b>"
        out = Util.truncate_html(s, 100)
        self.assertLessEqual(len(out), 100)
        self.assertTrue(out.rstrip().endswith("</b>"))

    def test_drops_dangling_partial_tag(self):
        s = "abc<b" + "x" * 200
        out = Util.truncate_html(s, 6)
        self.assertNotIn("<b", out.replace("[truncated]", ""))


if __name__ == '__main__':
    unittest.main()
