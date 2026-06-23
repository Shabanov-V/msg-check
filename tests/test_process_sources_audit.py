"""Seam-B regression tests for the Silent-skip bug (ADR 0006).

The cursor must advance iff a decision_log row is written for every message a
batch passed. A batch the LLM judged all-irrelevant must still leave skipped
rows; a batch whose LLM call failed must NOT advance the cursor.
"""
import os
import sys
import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model.unifiedMessage import UnifiedMessage
from model.chatInfo import ChatInfo
from service.dbService import DBService
from service.runContext import RunContext
from service.messageService import MessageService
from service.textAnalyzer import TextAnalyzer
from tests.test_find_messages import FakeClient as FakeLLMClient, FakeCompletions, FakeCompletion

CHAT_ID = "777"
DIALOG_ID = "telegram:777"


class FakeSource:
    source_name = "telegram"

    def __init__(self, messages):
        self._messages = messages

    async def get_target_chats(self):
        return [ChatInfo(source="telegram", chat_id=CHAT_ID, chat_title="IT chat")]

    async def fetch_messages(self, chat):
        return self._messages

    def get_message_reference(self, message):
        return ""


class FakeAnalyzer:
    """findMessages returns a fixed result or raises."""
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def findMessages(self, text):
        if self._exc is not None:
            raise self._exc
        return self._result


class FakeClient:
    def __init__(self):
        self.sent = []

    async def send_message(self, peer, message):
        self.sent.append((peer, message))


def make_message(mid="500", text="мы идем в хайк в воскресенье"):
    return UnifiedMessage(
        source="telegram", chat_id=CHAT_ID, chat_title="IT chat",
        message_id=mid, text=text,
        timestamp=datetime(2026, 6, 23, 17, 55, tzinfo=timezone.utc),
    )


def build_service(analyzer):
    db_path = tempfile.mktemp(suffix=".db")
    db = DBService(db_path)
    env = SimpleNamespace(
        error_dialog_id=123, output_dialog_id=456,
        timezone="Europe/Madrid", base_prompt="p1", llm_model="fake-model",
    )
    svc = MessageService(FakeClient(), db, analyzer, calendar_service=None, env=env)
    return svc, db


EMPTY_RESULT = {
    "results": [], "Events": [], "borderline": [],
    "_meta": {"phase1_duration_sec": 0.0, "phase2_duration_sec": 0.0,
              "phase1_tokens": None, "phase2_tokens": None},
}


def make_real_analyzer(llm_outputs):
    return TextAnalyzer(
        key="x", base_prompt="p1", phase2_prompt="p2", model="fake-model",
        client=FakeLLMClient(FakeCompletions(llm_outputs)),
    )


class TestAllIrrelevantBatch(unittest.TestCase):
    def test_found_false_writes_skipped_row_and_advances_cursor(self):
        # End-to-end through the REAL TextAnalyzer: the LLM judges the batch
        # all-irrelevant (found=false). This is the exact scenario that silently
        # dropped the hike message. It must leave a skipped row, not vanish.
        analyzer = make_real_analyzer(
            [FakeCompletion('{"found": false, "results": [], "borderline": []}')]
        )
        svc, db = build_service(analyzer)
        run_ctx = RunContext()
        msg = make_message()

        asyncio.run(svc.process_sources([FakeSource([msg])], [], run_ctx))

        run_id = run_ctx.start_time.isoformat()
        rows = db.get_decision_rows(run_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["phase1_verdict"], "skipped")
        self.assertEqual(rows[0]["message_id"], "500")

        self.assertEqual(db.get_last_processed_message(DIALOG_ID), 500)


class TestFailedBatch(unittest.TestCase):
    def test_analyzer_failure_freezes_cursor_and_records_error(self):
        analyzer = FakeAnalyzer(exc=RuntimeError("LLM down"))
        svc, db = build_service(analyzer)
        run_ctx = RunContext()
        msg = make_message()

        asyncio.run(svc.process_sources([FakeSource([msg])], [], run_ctx))

        # Cursor must NOT advance — the message was never classified.
        self.assertIsNone(db.get_last_processed_message(DIALOG_ID))
        # No decision_log rows for a failed batch.
        self.assertEqual(db.get_decision_rows(run_ctx.start_time.isoformat()), [])
        # Failure is visible, not silent.
        self.assertTrue(run_ctx.errors)


if __name__ == "__main__":
    unittest.main()
