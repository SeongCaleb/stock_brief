import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from v4_community import parse_wepoll_listing, parse_youtube_feed, collect_public_signals
from v4_email import make_digest
from v3_market_data import _detail_metrics


class PublicSourceTests(unittest.TestCase):
    def test_wepoll_listing_deduplicates_and_filters(self):
        html = """<a href='/g2/bbs/board.php?bo_table=news&amp;wr_id=12345'>국채 금리 상승과 반도체 투자 논란</a>
        <a href='/g2/bbs/board.php?bo_table=news&amp;wr_id=12345'>국채 금리 상승과 반도체 투자 논란</a>
        <a href='/g2/bbs/board.php?bo_table=stock&amp;wr_id=77'>ETF와 시장 위험을 비교해봄</a>
        <a href='https://evil.example/?bo_table=news&amp;wr_id=999'>모조 링크 무시</a>"""
        result = parse_wepoll_listing(html, "news", "https://wepoll.kr/g2/bbs/board.php?bo_table=news")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "wepoll:news:12345")

    def test_wepoll_economy_noise_removed(self):
        h = """<a href='/g2/bbs/board.php?bo_table=stock&amp;wr_id=123'>밥을 어디서 먹을까 오늘저녁</a>
        <a href='/g2/bbs/board.php?bo_table=stock&amp;wr_id=124'>국채 금리 변동과 금융주 매수 생각</a>"""
        result = parse_wepoll_listing(h, "stock", "https://wepoll.kr/g2/bbs/board.php?bo_table=stock")
        self.assertEqual(len(result), 1)
        self.assertIn("124", result[0]["id"])

    def test_youtube_feed_title_only(self):
        xml = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
         <entry><id>yt:video:abc123</id><title>미국 증시 라이브 금리 발표</title>
         <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
         <published>2026-10-23T15:00:00+00:00</published></entry></feed>"""
        found = parse_youtube_feed(xml, datetime(2026, 10, 24, 1, tzinfo=timezone.utc))
        self.assertEqual(len(found), 1)
        self.assertIn("제목", found[0]["basis"])

    def test_public_fetch_failure_is_honest(self):
        session = Mock()
        session.get.side_effect = TimeoutError("offline")
        result = collect_public_signals(session=session, now=datetime(2026, 10, 24, tzinfo=timezone.utc))
        self.assertEqual(result["items"], [])
        self.assertIn("접근 불가", result["statuses"]["위폴 뉴스"])
        self.assertIn("반영 안 됨", result["statuses"]["아카라이브 주식 채널"])

    def test_company_data_rendering(self):
        example = {"name": "Example", "ticker": "EXM", "status": "조사 후보",
                   "evidence": "제한적", "quote_date": "2026-10-23",
                   "risk_tags": [], "sources": ["https://finance.yahoo.com/quote/EXM/"],
                   "bull_case": "성장 가설", "bear_case": "가격 위험", "entry_condition": "실적 확인",
                   "market_info": {"return_3m_pct": 11, "below_52w_high_pct": -7},
                   "detail": {"revenue_growth_yoy_pct": 15.0, "fcf_yield_pct": 3.1},
                   "valuation_info": {"forward_pe": 22.4}}
        community = {"items": [{"source": "위폴 뉴스", "title": "금리 토론", "url": "https://wepoll.kr/a",
                                "basis": "공개 게시판 제목"}],
                     "statuses": {"아카라이브 주식 채널": "접근 제한"}}
        _, html = make_digest([], {"macro": {}, "assets": {}, "watchlist": [], "asset_classes": []},
                              "판단 보류", [example], community=community)
        self.assertIn("FCF 수익률", html)
        self.assertIn("위폴 뉴스", html)
        self.assertIn("접근 제한", html)

    def test_vendor_fundamentals_not_fabricated(self):
        output = _detail_metrics({"revenueGrowth": 0.125, "freeCashflow": 100_000_000,
                                  "marketCap": 5_000_000_000}, "Technology")
        self.assertEqual(output["revenue_growth_yoy_pct"], 12.5)
        self.assertEqual(output["fcf_yield_pct"], 2)
        self.assertIsNone(output["operating_margin_pct"])


if __name__ == "__main__":
    unittest.main()
