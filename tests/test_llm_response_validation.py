import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from service.textAnalyzer import validate_completion


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content, finish_reason):
        self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeCompletion:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [FakeChoice(content, finish_reason)]


class TestValidateCompletion(unittest.TestCase):
    def test_truncated_response_raises_instead_of_returning_garbage(self):
        # Model hit the token cap mid-JSON: finish_reason == 'length'.
        # The half-written JSON would crash json.loads downstream, so validation
        # must reject it up front and let the retry path handle it.
        truncated = '{"found": true, "results": [{"text": "Quiz in Mad'
        completion = FakeCompletion(truncated, finish_reason="length")

        with self.assertRaises(ValueError):
            validate_completion(completion)

    def test_empty_content_raises(self):
        # Model returned no content at all (the old 'NoneType startswith' crash).
        completion = FakeCompletion(None, finish_reason="stop")

        with self.assertRaises(ValueError):
            validate_completion(completion)

    def test_good_response_returns_content_stripped_of_code_fences(self):
        fenced = '```json\n{"found": false, "results": [], "borderline": []}\n```'
        completion = FakeCompletion(fenced, finish_reason="stop")

        content = validate_completion(completion)

        self.assertEqual(content, '{"found": false, "results": [], "borderline": []}')


if __name__ == "__main__":
    unittest.main()
