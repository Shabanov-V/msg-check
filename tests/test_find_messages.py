import os
import sys
import json
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from service.textAnalyzer import TextAnalyzer


class FakeUsage:
    total_tokens = 42


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeCompletion:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [FakeChoice(content, finish_reason)]
        self.usage = FakeUsage()


class FakeCompletions:
    """Returns queued completions; an Exception in the queue is raised."""
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def create(self, **kwargs):
        out = self.outputs[self.calls]
        self.calls += 1
        if isinstance(out, Exception):
            raise out
        return out


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, completions):
        self.chat = FakeChat(completions)


def make_analyzer(outputs):
    return TextAnalyzer(
        key="x",
        base_prompt="p1",
        phase2_prompt="p2",
        model="fake-model",
        client=FakeClient(FakeCompletions(outputs)),
    )


# One message, serialized the way MessageService hands it to the analyzer.
INPUT = json.dumps([{
    "source": "telegram", "chat_id": "1", "chat_title": "IT chat",
    "text": "мы идем в хайк в воскресенье", "message_id": "m0",
    "datetime": "2026-06-23 17:55:00",
}])


class TestFindMessagesNoHits(unittest.TestCase):
    def test_found_false_returns_empty_result_not_none(self):
        # LLM succeeded and judged the whole batch irrelevant. This is NOT a
        # failure: callers must still get a valid (empty) result so a skipped
        # decision_log row is written and the cursor advances. Returning None
        # here is the "Silent skip" bug (ADR 0006).
        completion = FakeCompletion('{"found": false, "results": [], "borderline": []}')
        analyzer = make_analyzer([completion])

        result = analyzer.findMessages(INPUT)

        self.assertIsNotNone(result)
        self.assertEqual(result["results"], [])
        self.assertEqual(result["Events"], [])
        self.assertEqual(result["borderline"], [])


class TestFindMessagesFailure(unittest.TestCase):
    def test_llm_failure_raises_instead_of_returning_none(self):
        # Phase 1 ultimately failed (LLM/parse error after retries). The caller
        # must NOT mistake this for "nothing relevant": findMessages raises so
        # MessageService freezes the cursor and the batch is retried next run.
        # (Patch the inner call to fail fast; the real retry is 10x30s.)
        analyzer = make_analyzer([])

        def boom(*a, **k):
            raise RuntimeError("LLM down")

        analyzer._TextAnalyzer__generate_content_with_retry = boom

        with self.assertRaises(Exception):
            analyzer.findMessages(INPUT)


if __name__ == "__main__":
    unittest.main()
