import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.review_decisions import (
    is_disagreement,
    eval_items_from_labeled,
    merge_eval_items,
    phase1_to_pred,
)


class TestDisagreement(unittest.TestCase):
    def test_reported_judged_not_is_disagreement(self):
        # Phase-1 reported (predicts relevant), judge says not -> false positive candidate.
        self.assertTrue(is_disagreement(
            {"phase1_verdict": "reported", "judge_verdict": "not"}))

    def test_skipped_judged_relevant_is_disagreement(self):
        # Phase-1 skipped (predicts not), judge says relevant -> false negative candidate.
        self.assertTrue(is_disagreement(
            {"phase1_verdict": "skipped", "judge_verdict": "relevant"}))

    def test_agreement_is_not_flagged(self):
        self.assertFalse(is_disagreement(
            {"phase1_verdict": "reported", "judge_verdict": "relevant"}))

    def test_unjudged_is_not_flagged(self):
        self.assertFalse(is_disagreement(
            {"phase1_verdict": "skipped", "judge_verdict": None}))


class TestEvalExport(unittest.TestCase):
    def test_only_human_labeled_rows_exported_with_predicted_frozen(self):
        rows = [
            {"source": "telegram", "chat_id": "1", "message_id": "10",
             "chat_title": "A", "text": "quiz", "phase1_verdict": "reported",
             "human_label": "not"},                       # confirmed false positive
            {"source": "telegram", "chat_id": "2", "message_id": "20",
             "chat_title": "B", "text": "chitchat", "phase1_verdict": "skipped",
             "human_label": None},                        # unconfirmed -> excluded
        ]
        items = eval_items_from_labeled(rows)
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["label"], "not")
        self.assertEqual(it["predicted"], "relevant")     # phase1 reported, frozen
        self.assertTrue(it["system_reported"])

    def test_relabel_keeps_latest(self):
        rows = [
            {"source": "telegram", "chat_id": "1", "message_id": "10", "chat_title": "A",
             "text": "x", "phase1_verdict": "skipped", "human_label": "not"},
            {"source": "telegram", "chat_id": "1", "message_id": "10", "chat_title": "A",
             "text": "x", "phase1_verdict": "skipped", "human_label": "relevant"},
        ]
        items = eval_items_from_labeled(rows)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["label"], "relevant")

    def test_merge_skips_existing(self):
        existing = [{"chat_title": "A", "text": "quiz", "label": "relevant"}]
        new = [
            {"chat_title": "A", "text": "quiz", "label": "relevant"},   # dup
            {"chat_title": "B", "text": "concert", "label": "relevant"},  # new
        ]
        merged = merge_eval_items(existing, new)
        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
