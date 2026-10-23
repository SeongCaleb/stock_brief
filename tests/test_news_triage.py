import unittest
from unittest.mock import patch
import summarize


class NewsTriageTests(unittest.TestCase):
    def test_extra_text_around_valid_array(self):
        data = '선별 결과: ```json\\n[{"index": 1, "signal": "주의", "reason": "금리"}]\\n```'
        self.assertEqual(summarize._parse_json_array(data)[0]["index"], 1)

    def test_bad_model_does_not_promote_unimportant_latest(self):
        items = [
            {"title": "Here is how to get richer before retirement", "summary": "A savings advice column", "source": "A"},
            {"title": "Small local cafe reports earnings", "summary": "An insignificant earnings update", "source": "B"},
            {"title": "Federal Reserve announces major interest rate decision", "summary": "Treasury yields move", "source": "C"},
        ]
        with patch.object(summarize, "_call", return_value="not valid JSON"):
            output = summarize.triage(items)
        self.assertEqual(len(output), 1)
        self.assertIn("Federal Reserve", output[0]["title"])
        self.assertIn("임시 분류", output[0]["signal_reason"])

    def test_failure_can_return_no_articles(self):
        items = [{"title": "A casual personal essay", "summary": "About gardening",
                  "source": "D"}]
        with patch.object(summarize, "_call", return_value="[broken"):
            self.assertEqual(summarize.triage(items), [])


if __name__ == "__main__":
    unittest.main()
