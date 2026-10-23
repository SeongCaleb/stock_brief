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

    def test_one_vendor_source_is_enough_for_research_idea(self):
        now = datetime(2026, 10, 23, 16, tzinfo=timezone.utc)
        price = {"price": 120, "as_of": "2026-10-23T00:00:00+00:00",
                 "source_url": "https://finance.yahoo.com/quote/XYZ/"}
        data = {"assets": {"XYZ": {
            "name": "Example Research",
            "market": price,
            "financials": {"as_of": price["as_of"], "source_url": price["source_url"],
                           "forward_pe": 18, "expected_earnings_growth_pct": None,
                           "peer_forward_pe_median": None},
            "thesis": {"bull_case": "장기 매출 성장 가설", "bear_case": "마진 악화 위험",
                       "entry_condition": "실적 확인", "invalidation": "성장률 하락",
                       "source_urls": ["https://finance.yahoo.com/quote/XYZ/"]},
        }}}
        with tempfile.TemporaryDirectory() as path:
            file = Path(path) / "data.json"
            file.write_text(json.dumps(data), encoding="utf-8")
            _, picks = research_snapshot(str(file), now=now)
            self.assertEqual(len(picks), 1)
            self.assertEqual(picks[0]["status"], "조사 후보")
            self.assertEqual(picks[0]["evidence"], "제한적")
            self.assertNotIn("매수 조건 검토", picks[0]["status"])

    def test_expensive_stock_warned_instead_of_hidden(self):
        now = datetime(2026, 10, 23, 16, tzinfo=timezone.utc)
        date = "2026-10-23T00:00:00+00:00"
        data = {"assets": {"ABC": {
            "name": "Example Expensive Stock",
            "market": {"price": 210, "as_of": date,
                       "source_url": "https://finance.yahoo.com/quote/ABC/"},
            "financials": {"as_of": date,
                           "source_url": "https://finance.yahoo.com/quote/ABC/",
                           "forward_pe": 60, "peer_forward_pe_median": 20,
                           "expected_earnings_growth_pct": 8},
            "thesis": {"bull_case": "성장 가설", "bear_case": "가격 위험",
                       "entry_condition": "실적 재확인", "invalidation": "전망 하향",
                       "source_urls": ["https://finance.yahoo.com/quote/ABC/"]},
        }}}
        with tempfile.TemporaryDirectory() as path:
            file = Path(path) / "data.json"
            file.write_text(json.dumps(data), encoding="utf-8")
            _, picks = research_snapshot(str(file), now=now)
            self.assertEqual(len(picks), 1)
            self.assertEqual(picks[0]["status"], "가격·과열 주의")
            self.assertTrue(picks[0]["risk_tags"])

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
