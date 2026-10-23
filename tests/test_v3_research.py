import calendar
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from v3_research import dated_articles, research_snapshot, research_html


class ResearchTests(unittest.TestCase):
    def test_personal_finance_excluded(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        when = datetime(2026, 10, 22, tzinfo=timezone.utc).timetuple()
        data = [
            {"title": "Should I put $20000 into a CD account?",
             "summary": "Personal financial advice about how to save for retirement.", "published": when},
            {"title": "Global central bank cuts interest rates",
             "summary": "Policy statement changes financing conditions and bond market expectations.", "published": when},
        ]
        result = dated_articles(data, now=now)
        self.assertEqual(len(result), 1)
        self.assertIn("central bank", result[0]["title"])

    def test_no_market_data_never_recommends(self):
        with tempfile.TemporaryDirectory() as path:
            f = Path(path) / "snapshot.json"
            f.write_text(json.dumps({"macro": {}, "assets": {}}), encoding="utf-8")
            regime, candidates = research_snapshot(str(f))
            self.assertIn("판단 보류", regime)
            self.assertEqual(candidates, [])
            self.assertIn("추천 보류", research_html(regime, candidates, False))

    def test_old_article_rejected(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        old = datetime(2026, 10, 1, tzinfo=timezone.utc).timetuple()
        self.assertFalse(dated_articles([{
            "title": "Markets are responding to central bank policy",
            "summary": "The economic policy change is an important market event.",
            "published": old
        }], now=now))


if __name__ == "__main__":
    unittest.main()
