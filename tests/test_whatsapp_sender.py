import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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


if __name__ == '__main__':
    unittest.main()
