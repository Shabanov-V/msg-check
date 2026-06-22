"""DBService read methods return rows accessible by column name, not position.

Locks the named-access contract that reportGenerator (run_history) and
MessageService (calendar_events) depend on, so a schema reorder can't silently
shift what callers read."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from service.dbService import DBService
from service.runContext import RunContext


class TestNamedDBRows(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = DBService(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_calendar_event_row_reads_by_name(self):
        start = datetime(2026, 6, 22, 20, 0)
        self.db.store_calendar_event(
            dialog_id="telegram:1", event_id="m1", title="Meetup",
            start_time=start, end_time=start, description="d",
            google_event_id="g123",
        )
        rows = self.db.get_events_starting_around(start, window_minutes=120)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Meetup")
        self.assertEqual(rows[0]["google_event_id"], "g123")

    def test_run_history_row_reads_by_name(self):
        ctx = RunContext()
        ctx.record_messages_fetched("telegram", "1", "Chat", 10)
        ctx.record_match("m1", "Chat", "hi", "reason", source="telegram", chat_id="1")
        ctx.finalize(ctx.start_time)
        self.db.store_run(ctx, verbosity="normal")

        rows = self.db.get_recent_runs(1)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["match_rate"], 0.1)
        self.assertIn("duration_sec", rows[0].keys())
        self.assertEqual(rows[0]["hallucination_recoveries"], 0)


if __name__ == "__main__":
    unittest.main()
