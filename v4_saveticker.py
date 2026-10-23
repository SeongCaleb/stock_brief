"""Public SaveTicker headline discovery, preferred editorial input.

No authentication, undocumented API calls, login bypass or copyrighted full-text
republishing. The JavaScript news listing may expose no static article anchors.
A publisher-restricted Google News RSS feed is an optional public fallback.
Only articles with verifiable timestamps become primary news candidates.
"""
from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import feedparser
import requests

SITE = "https://saveticker.com/news"
GOOGLE_RSS = ("https://news.google.com/rss/search"
              "?q=site%3Asaveticker.com%2Fnews%20when%3A2d"
              "&hl=ko&gl=KR&ceid=KR:ko")
HEADERS = {"User-Agent": "StockBriefResearch/1.0 (public editorial headlines)"}
DETAIL_PATTERN = re.compile(r"^/news/(?:news_[A-Za-z0-9_-]+|[0-9]+)$")
RUMOR_OR_REMOVED = re.compile(r"카더라|미확인 루머|찌라시|원문 삭제|기사 삭제|출처 불명|확인되지 않은 소문", re.I)


class NewsLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.label = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data):
        if self.href is not None:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            title = " ".join(" ".join(self.label).split())
            link = urljoin(SITE, self.href)
            split = urlsplit(link)
            if split.hostname in ("saveticker.com", "www.saveticker.com") and DETAIL_PATTERN.match(split.path):
                if len(title) >= 12:
                    self.links.append({"title": title[:180], "link": link})
            self.href = None
            self.label = []


def parse_public_links(html):
    p = NewsLinks()
    p.feed(html)
    distinct = {}
    for item in p.links:
        distinct[item["link"]] = item
    return list(distinct.values())


def parse_indexed_feed(xml, now=None):
    now = now or datetime.now(timezone.utc)
    entries = feedparser.parse(xml)
    result = []
    for a in entries.entries:
        title = str(a.get("title") or "").strip()
        source = a.get("source") or {}
        source_url = str(source.get("href") or source.get("url") or "")
        source_title = str(source.get("title") or "")
        origin = urlsplit(source_url).hostname or ""
        if origin not in ("saveticker.com", "www.saveticker.com"):
            # Google News search may return loosely related publisher links.
            if "세이브티커" not in source_title and "saveticker" not in source_title.lower():
                continue
        ts = a.get("published_parsed")
        if not ts or len(title) < 12 or RUMOR_OR_REMOVED.search(title):
            continue
        age = (now.timestamp() - calendar.timegm(ts)) / 3600
        if age < -2 or age > 72:
            continue
        link = str(a.get("link") or "")
        if urlsplit(link).scheme != "https":
            continue
        # Aggregator article links remain Google links unless a direct link is provided.
        result.append({
            "title": title[:180],
            "summary": re.sub(r"<[^>]+>", " ", str(a.get("summary") or ""))[:350],
            "source": "세이브티커 (검색 피드)",
            "market": "US",
            "published": ts,
            "link": link,
            "uid": "saveticker-indexed:" + (str(a.get("id") or link))[:250],
            "basis": "세이브티커 게시물의 검색 색인 제목·발행 시각 (원문 검증 별도)",
        })
    return result[:25]


def collect_saveticker(session=None, now=None):
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    status = []
    static = []
    feed = []
    try:
        response = session.get(SITE, headers=HEADERS, timeout=12)
        response.raise_for_status()
        static = parse_public_links(response.text)
        status.append(f"공개 뉴스 페이지 접근 성공, 정적 기사 링크 {len(static)}개")
    except Exception as exc:
        status.append("공개 뉴스 페이지 접근 실패: " + type(exc).__name__)
    try:
        response = session.get(GOOGLE_RSS, headers=HEADERS, timeout=12)
        response.raise_for_status()
        feed = parse_indexed_feed(response.text, now=now)
        status.append(f"세이브티커 뉴스 검색 피드에서 날짜 검증된 기사 {len(feed)}건")
    except Exception as exc:
        status.append("세이브티커 인덱스 피드 접근 실패: " + type(exc).__name__)
    return {
        "articles": feed,
        # Static listing links without a date cannot be asserted as today's news.
        "listing": static[:10],
        "status": " · ".join(status),
    }
