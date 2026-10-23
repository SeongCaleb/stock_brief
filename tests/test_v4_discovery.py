import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from v4_discovery import (
    SECTORS, discovery_universe, identify_news_tickers,
    unique_events, next_tracking, tracking_changes, diversify_candidates,
)
from v4_email import make_digest


class DiscoveryTests(unittest.TestCase):
    def test_covers_every_sector(self):
        day = date(2026, 10, 24)
        names = discovery_universe([], on_day=day)
        self.assertEqual(len(SECTORS), 11)
        self.assertEqual(len(names), 11)
        for ticker, group in zip(names, SECTORS.values()):
            self.assertIn(ticker, group)

    def test_rotates_daily(self):
        first = discovery_universe([], date(2026, 10, 24))
        second = discovery_universe([], date(2026, 10, 25))
        self.assertNotEqual(first, second)
        self.assertEqual(first, discovery_universe([], date(2026, 10, 24)))

    def test_news_discovers_extra_company(self):
        articles = [{"title": "Palantir expands defense contracts",
                     "summary": "NASDAQ: PLTR is preparing a new platform."}]
        found = identify_news_tickers(articles)
        self.assertIn("PLTR", found)
        self.assertIn("PLTR", discovery_universe(articles, date(2026, 10, 24)))

    def test_never_treats_ai_as_symbol(self):
        found = identify_news_tickers([{"title": "AI boom as markets recover"}])
        self.assertNotIn("AI", found)

    def test_duplicate_title_removed(self):
        news = [
            {"title": "US Treasury yields rise as inflation fears spread", "summary": ""},
            {"title": "Inflation fears spread as US Treasury yields rise", "summary": ""},
            {"title": "Drug company announces clinical trial result", "summary": ""},
        ]
        self.assertEqual(len(unique_events(news)), 2)

    def test_tracking_only_price_change(self):
        prev = {"latest": {"ABC": {"price": 100.0}}}
        snap = {"assets": {"ABC": {
            "market": {"price": 110, "source_url": "https://example.com"},
            "financials": {"forward_pe": 12, "expected_earnings_growth_pct": 8}
        }}}
        self.assertIn("10.0%", tracking_changes(snap, prev)[0])
        state = next_tracking(snap, prev, "2026-10-24")
        self.assertEqual(state["latest"]["ABC"]["date"], "2026-10-24")

    def test_diversify(self):
        data = [{"ticker": "A", "sector": "Tech"}, {"ticker": "B", "sector": "Tech"},
                {"ticker": "C", "sector": "Health"}, {"ticker": "D", "sector": "Energy"}]
        self.assertEqual([x["ticker"] for x in diversify_candidates(data)], ["A", "C", "D"])

    def test_compact_html(self):
        dt = datetime(2026, 10, 24, 1, tzinfo=timezone.utc)
        news = [{"title": "Rate news", "source": "Example", "link": "https://source.example/1",
                 "brief": "⚠️ 주의 · 금리 변화\n시장 영향에 주목.\n🎯 금리 확인"}]
        snapshot = {"assets": {}, "watchlist": [], "collection_warnings": [],
                    "asset_classes": [{"ticker": "VOO", "name": "S&P 500", "return_3m_pct": 2.5,
                                      "as_of": "2026-10-23T00:00:00+00:00"}]}
        _, html = make_digest(news, snapshot, "자료 부족", [], generated_at=dt)
        self.assertIn("금리 변화", html)
        self.assertEqual(html.count("Rate news"), 0)
        self.assertEqual(html.count("금리 변화"), 1)
        self.assertIn("추천", html)
        self.assertIn("VOO", html)
        self.assertIn("2026-10-24", html)


if __name__ == "__main__":
    unittest.main()
