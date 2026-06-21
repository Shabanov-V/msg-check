import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model.unifiedMessage import UnifiedMessage
from service.llmJoin import resolve_llm_results
from service.decisionLog import build_decision_rows


def msg(chat_id, message_id, text, chat_title="Chat"):
    return UnifiedMessage(
        source="telegram",
        chat_id=chat_id,
        chat_title=chat_title,
        message_id=message_id,
        text=text,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def by_id(rows):
    return {(r["source"], r["chat_id"], r["message_id"]): r for r in rows}


class TestVerdictAssignment(unittest.TestCase):
    def test_every_fetched_message_gets_a_verdict(self):
        reported = msg("100", "1", "Quiz in Madrid", "A")
        border = msg("200", "2", "maybe meetup", "B")
        skipped = msg("300", "3", "chitchat", "C")
        messages = [reported, border, skipped]

        response = {
            "results": [{"message_id": "m0", "reason": "quiz event"}],
            "borderline": [{"message_id": "m1", "exclusion_reason": "no time"}],
        }
        resolved = resolve_llm_results(messages, response)

        rows = build_decision_rows(
            messages, resolved, dedup_keys=set(),
            run_id="r1", llm_model="deepseek", prompt_version="v1",
        )

        self.assertEqual(len(rows), 3)  # all fetched messages logged
        idx = by_id(rows)
        self.assertEqual(idx[("telegram", "100", "1")]["phase1_verdict"], "reported")
        self.assertEqual(idx[("telegram", "100", "1")]["phase1_reason"], "quiz event")
        self.assertEqual(idx[("telegram", "200", "2")]["phase1_verdict"], "borderline")
        self.assertEqual(idx[("telegram", "200", "2")]["phase1_reason"], "no time")
        self.assertEqual(idx[("telegram", "300", "3")]["phase1_verdict"], "skipped")


class TestDecisionLogPersistence(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        from service.dbService import DBService
        self.db = DBService(db_path=self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_store_and_read_back_rows(self):
        reported = msg("100", "1", "Quiz in Madrid", "A")
        skipped = msg("100", "2", "chitchat", "A")
        messages = [reported, skipped]
        response = {"results": [{"message_id": "m0", "reason": "quiz"}]}
        resolved = resolve_llm_results(messages, response)
        rows = build_decision_rows(
            messages, resolved, dedup_keys=set(),
            run_id="r1", llm_model="deepseek", prompt_version="v1",
        )

        self.db.store_decision_log(rows)
        got = self.db.get_decision_rows(run_id="r1")

        self.assertEqual(len(got), 2)
        idx = {(r["source"], r["chat_id"], r["message_id"]): r for r in got}
        self.assertEqual(idx[("telegram", "100", "1")]["phase1_verdict"], "reported")
        self.assertEqual(idx[("telegram", "100", "1")]["text"], "Quiz in Madrid")
        self.assertEqual(idx[("telegram", "100", "2")]["phase1_verdict"], "skipped")
        # judge/human columns start empty
        self.assertIsNone(idx[("telegram", "100", "1")]["judge_verdict"])
        self.assertIsNone(idx[("telegram", "100", "1")]["human_label"])

    def test_unjudged_rows_then_set_judge_verdict(self):
        messages = [msg("100", "1", "Quiz in Madrid", "A"), msg("100", "2", "chitchat", "A")]
        response = {"results": [{"message_id": "m0", "reason": "quiz"}]}
        resolved = resolve_llm_results(messages, response)
        self.db.store_decision_log(build_decision_rows(
            messages, resolved, dedup_keys=set(),
            run_id="r1", llm_model="m", prompt_version="v1",
        ))

        unjudged = self.db.get_unjudged_rows()
        self.assertEqual(len(unjudged), 2)

        # Judge the reported one as actually-not-relevant (a false positive).
        target = next(r for r in unjudged if r["message_id"] == "1")
        self.db.set_judge_verdict(target["id"], "not")

        still = self.db.get_unjudged_rows()
        self.assertEqual(len(still), 1)
        self.assertEqual(still[0]["message_id"], "2")

        judged = next(r for r in self.db.get_decision_rows("r1") if r["message_id"] == "1")
        self.assertEqual(judged["judge_verdict"], "not")

    def test_sender_name_not_stored(self):
        rows = build_decision_rows(
            [msg("100", "1", "hi", "A")], resolve_llm_results([msg("100", "1", "hi", "A")], {}),
            dedup_keys=set(), run_id="r1", llm_model="m", prompt_version="v1",
        )
        self.assertNotIn("sender_name", rows[0])


class TestFeedAction(unittest.TestCase):
    def test_reported_but_dedup_skipped_is_marked(self):
        sent = msg("100", "1", "Quiz tonight", "A")
        deduped = msg("200", "2", "Quiz tonight (repost)", "B")
        messages = [sent, deduped]

        response = {"results": [
            {"message_id": "m0", "reason": "quiz"},
            {"message_id": "m1", "reason": "quiz dup"},
        ]}
        resolved = resolve_llm_results(messages, response)

        # deduped was reported by Phase-1 but suppressed from the feed.
        rows = build_decision_rows(
            messages, resolved,
            dedup_keys={("telegram", "200", "2")},
            run_id="r1", llm_model="deepseek", prompt_version="v1",
        )
        idx = by_id(rows)
        self.assertEqual(idx[("telegram", "100", "1")]["feed_action"], "sent")
        self.assertEqual(idx[("telegram", "200", "2")]["feed_action"], "dedup_skipped")
        # both still count as reported by Phase-1
        self.assertEqual(idx[("telegram", "200", "2")]["phase1_verdict"], "reported")


if __name__ == "__main__":
    unittest.main()
