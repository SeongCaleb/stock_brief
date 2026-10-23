"""Read-only public watch sources for Stock Brief.

Official public lists only; no login, bypass or scraping hidden content.
Wepoll board timestamps are often relative/ambiguous, so a new post means
"first seen by our collector", NOT "published today".
YouTube RSS provides the video title, not a transcript or verified video claim.
"""
from __future__ import annotations

import calendar
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import feedparser
import requests

BASE = "https://wepoll.kr"
WEPOLL = {
    "위폴 뉴스": BASE + "/g2/bbs/board.php?bo_table=news",
    "위폴 경제": BASE + "/g2/bbs/board.php?bo_table=stock",
}
YOUTUBE_ID = "UC_JJ_NhRqPKcIOj5Ko3W_3w"
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=" + YOUTUBE_ID
ARCA_URL = "https://arca.live/b/stock"
STATE_FILE = "v4_community_seen.json"
HEADERS = {"User-Agent": "StockBriefPublicResearch/1.0 (+https://github.com/SeongCaleb/stock_brief)"}


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            title = re.sub(r"\s+", " ", "".join(self._text)).strip()
            self.anchors.append((self._href, title))
            self._href = None
            self._text = []


def parse_wepoll_listing(html, category, page_url):
    parser = AnchorParser()
    parser.feed(html)
    result, seen = [], set()
    for href, title in parser.anchors:
        full = urljoin(page_url, href)
        u = urlsplit(full)
        query = parse_qs(u.query)
        if u.hostname not in ("wepoll.kr", "www.wepoll.kr"):
            continue
        if query.get("bo_table", [None])[0] != category:
            continue
        post_id = query.get("wr_id", [None])[0]
        if post_id is None or not post_id.isdecimal():
            continue
        if len(title) < 10 or title in ("댓글", "이전글", "다음글") or post_id in seen:
            continue
        if category == "stock" and not re.search(
            r"주식|증시|증권|국장|미장|금리|환율|환전|채권|국채|ETF|종목|반도체|실적|"
            r"투자|고평가|저평가|레버리지|인버스|원유|유가|AI|코스피|나스닥|"
            r"삼성|하이닉스|엔비디아|마이크로소프트|구글|알파벳|애플|"
            r"테슬라|경제|물가|배당|매도|매수|금융|대출|인플레|인플레이션",
            title, re.I
        ):
            continue
        seen.add(post_id)
        result.append({"id": f"wepoll:{category}:{post_id}",
                       "source": "위폴 뉴스" if category == "news" else "위폴 경제",
                       "title": title[:160],
                       "url": full, "basis": "공개 게시판 제목(게시일 미검증)"})
    return result


def parse_youtube_feed(text, now=None):
    now = now or datetime.now(timezone.utc)
    parsed = feedparser.parse(text)
    if parsed.bozo and not parsed.entries:
        raise ValueError("Invalid YouTube feed")
    out = []
    for entry in parsed.entries:
        published = entry.get("published_parsed")
        if not published:
            continue
        age = (now.timestamp() - calendar.timegm(published)) / 3600
        if age < -2 or age > 168:
            continue
        link = str(entry.get("link") or "")
        if urlsplit(link).hostname not in ("www.youtube.com", "youtube.com"):
            continue
        out.append({"id": "youtube:" + str(entry.get("id") or link),
                    "source": "오선의 미국 증시 라이브",
                    "title": str(entry.get("title") or "")[:180],
                    "url": link, "published": entry.get("published"),
                    "basis": "공개 영상 제목(자막·영상 본문 미확인)"})
    return out[:8]


def load_seen(path=STATE_FILE):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def collect_public_signals(previous=None, session=None, now=None, max_items=9):
    now = now or datetime.now(timezone.utc)
    session = session or requests.Session()
    previous = previous or {}
    previous_ids = set(previous.get("seen_ids") or [])
    found, statuses, next_ids = [], {}, list(previous_ids)
    for label, url in WEPOLL.items():
        category = "news" if label.endswith("뉴스") else "stock"
        try:
            response = session.get(url, headers=HEADERS, timeout=14)
            response.raise_for_status()
            entries = parse_wepoll_listing(response.text, category, url)
            statuses[label] = f"공개 목록 {len(entries)}개 확인; 본문·게시 시각은 미확인"
            found.extend(entries[:10])
        except Exception as exc:
            statuses[label] = "접근 불가 (" + type(exc).__name__ + ")"
    try:
        response = session.get(YOUTUBE_FEED, headers=HEADERS, timeout=14)
        response.raise_for_status()
        entries = parse_youtube_feed(response.text, now=now)
        found.extend(entries)
        statuses["오선의 미국 증시 라이브"] = f"최근 7일 영상 제목 {len(entries)}개 확인; 자막 미확인"
    except Exception as exc:
        statuses["오선의 미국 증시 라이브"] = "피드 접근 불가 (" + type(exc).__name__ + ")"
    # Not attempting login, circumvention, or mirroring blocked content.
    statuses["아카라이브 주식 채널"] = "직접 수집 미연결(접근 제한); 반영 안 됨"
    fresh = []
    for item in found:
        if item["id"] not in previous_ids:
            fresh.append(item)
        if item["id"] not in next_ids:
            next_ids.append(item["id"])
    return {
        "items": fresh[:max_items],
        "statuses": statuses,
        "next_seen": {"seen_ids": next_ids[-800:],
                      "last_checked": now.isoformat()},
    }
