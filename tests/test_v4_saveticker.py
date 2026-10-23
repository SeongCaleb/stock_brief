import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from v4_saveticker import parse_public_links, parse_indexed_feed, collect_saveticker
from v4_deep_research import research_candidates
from v4_email import make_digest


class SaveTickerTests(unittest.TestCase):
    def test_public_listing_links_only(self):
        page = """<a href='/news/news_Abc123X'>AI 데이터센터 관련 기업 실적 발표</a>
        <a href='https://saveticker.com/news/234567'>미국 금리 전망 주요 분석 보도</a>
        <a href='https://evil.example/news/999'>잘못된 뉴스 출처 링크</a>
        <a href='/community/234'>커뮤니티 게시물</a>"""
        output = parse_public_links(page)
        self.assertEqual(len(output), 2)
        self.assertTrue(all(x["link"].startswith("https://saveticker.com/news/") for x in output))

    def test_index_only_matching_publisher_and_recent_items(self):
        xml = """<?xml version='1.0'?><rss version='2.0'><channel>
        <title>Google News</title>
        <item><title>연준 금리 전망 - 세이브티커</title>
        <link>https://news.google.com/rss/articles/first</link>
        <source url="https://saveticker.com">세이브티커</source>
        <pubDate>Fri, 23 Oct 2026 12:00:00 GMT</pubDate>
        <description>연준의 단기 금리 결정에 대한 새 의견과 불확실성</description></item>
        <item><title>잘못된 다른 뉴스 매체 제목</title>
        <link>https://news.google.com/rss/articles/second</link>
        <source url="https://random.example">Other</source>
        <pubDate>Fri, 23 Oct 2026 12:00:00 GMT</pubDate>
        </item></channel></rss>"""
        rows = parse_indexed_feed(xml, datetime(2026, 10, 24, tzinfo=timezone.utc))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "세이브티커 (검색 피드)")

    def test_explicit_rumor_is_not_promoted_to_news(self):
        xml = """<?xml version='1.0'?><rss version='2.0'><channel>
        <item><title>(카더라) 기업 인수합병 루머 - 세이브티커</title>
        <link>https://news.google.com/rss/articles/rumor</link>
        <source url="https://saveticker.com">세이브티커</source>
        <pubDate>Fri, 23 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
        self.assertEqual(parse_indexed_feed(xml, datetime(2026, 10, 24, tzinfo=timezone.utc)), [])

    def test_access_failure_does_not_generate_fake_news(self):
        session = Mock()
        session.get.side_effect = TimeoutError("network denied")
        out = collect_saveticker(session=session)
        self.assertEqual(out["articles"], [])
        self.assertEqual(out["listing"], [])
        self.assertIn("접근 실패", out["status"])


class DeepResearchTests(unittest.TestCase):
    def test_model_failure_falls_back_to_metrics(self):
        candidates = [{"ticker": "ABC", "name": "Example", "score": 10,
                       "quote_date": "2026-10-23"}]
        result = research_candidates(candidates, [], [], lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(result[0]["ticker"], "ABC")
        self.assertNotIn("deep_dive", result[0])

    def test_partial_batch_json_retries_individual_candidates(self):
        candidates = [{
            "ticker": "ABC", "name": "ABC",
            "quote_date": "2026-10-23", "market_info": {}, "detail": {},
            "valuation_info": {}, "risk_tags": []
        }]
        calls = []
        def caller(system, context, max_tokens):
            calls.append(max_tokens)
            if len(calls) == 1:
                return '[{"ticker":"ABC","why":"불완전한'
            return ('[{"ticker":"ABC","why":"수익성 개선 가능","catalyst":"다음 분기 실적",'
                    '"bear":"성장 둔화 위험","entry":"이익률 확인",'
                    '"exit":"실적 하향","alternative":"VOO 비교"}]')
        out = research_candidates(candidates, [], [], caller)
        self.assertEqual(len(calls), 2)
        self.assertEqual(out[0]["deep_dive"]["entry"], "이익률 확인")

    def test_batch_memo_renders_as_six_distinct_fields(self):
        candidate = {"ticker": "ABC", "name": "Example", "status": "조사 후보",
                     "score": 10, "evidence": "제한적", "quote_date": "2026-10-23",
                     "market_info": {}, "valuation_info": {}, "detail": {}, "sources": [],
                     "risk_tags": [], "bull_case": "정량 근거", "bear_case": "주가 위험",
                     "entry_condition": "실적 확인"}
        def caller(system, context, max_tokens):
            self.assertIn("3~6개월", system)
            self.assertIn("ABC", context)
            return '[{"ticker":"ABC","why":"기업 추정 성장","catalyst":"다음 분기 발표", "bear":"비용 증가", "entry":"실적 확인", "exit":"성장 둔화", "alternative":"VOO 비교"}]'
        enriched = research_candidates([candidate], [], [], caller)
        self.assertEqual(enriched[0]["deep_dive"]["bear"], "비용 증가")
        _, html = make_digest([], {"macro": {}, "assets": {}, "watchlist": [], "asset_classes": []},
                              "판단 보류", enriched)
        self.assertIn("대안 비교", html)
        self.assertIn("VOO 비교", html)


if __name__ == "__main__":
    unittest.main()
