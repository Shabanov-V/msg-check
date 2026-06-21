import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model.unifiedMessage import UnifiedMessage
from service.llmJoin import assign_handles, resolve_llm_results


def msg(chat_id, message_id, text, chat_title="Chat"):
    return UnifiedMessage(
        source="telegram",
        chat_id=chat_id,
        chat_title=chat_title,
        message_id=message_id,
        text=text,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestCollisionResolution(unittest.TestCase):
    def test_same_message_id_different_chats_resolve_to_right_message(self):
        # Two chats both number a message "1424" — the production collision.
        a = msg("100", "1424", "Quiz in Madrid tonight", "Chat A")
        b = msg("200", "1424", "unrelated chitchat", "Chat B")
        messages = [a, b]  # LLM-facing order

        # LLM reports only the first message, by its synthetic handle.
        response = {"results": [{"message_id": "m0", "reason": "quiz event"}]}

        resolved = resolve_llm_results(messages, response)

        self.assertEqual(len(resolved.matched), 1)
        m, reason = resolved.matched[0]
        self.assertIs(m, a)
        self.assertEqual(m.chat_title, "Chat A")
        self.assertEqual(reason, "quiz event")


class TestBorderlineResolution(unittest.TestCase):
    def test_borderline_handle_resolves_to_right_message(self):
        a = msg("100", "1424", "maybe a meetup?", "Chat A")
        b = msg("200", "1424", "chitchat", "Chat B")
        messages = [a, b]

        response = {
            "borderline": [
                {"message_id": "m0", "exclusion_reason": "no explicit time"}
            ]
        }

        resolved = resolve_llm_results(messages, response)

        self.assertEqual(len(resolved.borderline), 1)
        message, reason = resolved.borderline[0]
        self.assertIs(message, a)
        self.assertEqual(reason, "no explicit time")


class TestAssignHandles(unittest.TestCase):
    def test_overwrites_message_id_with_sequential_handles(self):
        objs = [
            {"message_id": "1424", "text": "a"},
            {"message_id": "1424", "text": "b"},  # colliding real id
            {"message_id": "9981", "text": "c"},
        ]
        out = assign_handles(objs)
        self.assertEqual([o["message_id"] for o in out], ["m0", "m1", "m2"])
        # original payload preserved
        self.assertEqual([o["text"] for o in out], ["a", "b", "c"])


class TestRecovery(unittest.TestCase):
    def test_duplicate_index_claim_routes_second_to_recovery(self):
        a = msg("100", "1424", "Quiz tonight", "Chat A")
        b = msg("200", "9981", "Concert Friday", "Chat B")
        messages = [a, b]

        # Model claims m0 twice; second claim must not re-grab message a.
        response = {
            "results": [
                {"message_id": "m0", "reason": "quiz"},
                {"message_id": "m0", "reason": "concert", "text": "Concert Friday"},
            ]
        }

        resolved = resolve_llm_results(messages, response)

        self.assertEqual(len(resolved.matched), 2)
        self.assertIs(resolved.matched[0][0], a)
        self.assertIs(resolved.matched[1][0], b)  # recovered to the right one
        self.assertEqual(resolved.recoveries, 1)

    def test_out_of_range_handle_recovered_by_text_match(self):
        a = msg("100", "1424", "Quiz in Madrid tonight", "Chat A")
        b = msg("200", "9981", "Concert on Friday", "Chat B")
        messages = [a, b]

        # Model garbled the handle ("m9" out of range) but echoed the text.
        response = {
            "results": [
                {"message_id": "m9", "reason": "concert", "text": "Concert on Friday"}
            ]
        }

        resolved = resolve_llm_results(messages, response)

        self.assertEqual(resolved.recoveries, 1)
        self.assertEqual(len(resolved.matched), 1)
        m, _ = resolved.matched[0]
        self.assertIs(m, b)
        self.assertEqual(resolved.still_missing, [])

    def test_unrecoverable_handle_listed_still_missing(self):
        a = msg("100", "1424", "Quiz in Madrid", "Chat A")
        messages = [a]

        response = {
            "results": [
                {"message_id": "m7", "reason": "?", "text": "nothing matches this"}
            ]
        }

        resolved = resolve_llm_results(messages, response)

        self.assertEqual(resolved.matched, [])
        self.assertEqual(resolved.recoveries, 0)
        self.assertEqual(resolved.still_missing, ["m7"])


class TestEventRestoration(unittest.TestCase):
    def test_event_handle_resolves_to_message_and_restores_real_id(self):
        a = msg("100", "1424", "Quiz in Madrid", "Chat A")
        b = msg("200", "1424", "chitchat", "Chat B")
        messages = [a, b]

        # Event references handle m0; its message_id must come back as the real id.
        response = {
            "results": [{"message_id": "m0", "reason": "quiz"}],
            "Events": [{"message_id": "m0", "title": "Quiz", "start_datetime": "x"}],
        }

        resolved = resolve_llm_results(messages, response)

        self.assertEqual(len(resolved.events), 1)
        message, event = resolved.events[0]
        self.assertIs(message, a)
        self.assertEqual(event["message_id"], "1424")  # real id restored, not "m0"
        self.assertEqual(event["title"], "Quiz")


if __name__ == "__main__":
    unittest.main()
