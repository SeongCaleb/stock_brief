"""RSS 수집 · 중복 제거 · 본문 추출 (미국 증시 전용)."""
import hashlib
import json
import os
import re
import time

import feedparser

try:
    import trafilatura
except Exception:  # trafilatura 미설치/로드 실패 시에도 파이프라인은 동작
    trafilatura = None

from config import FEEDS, MAX_CANDIDATES, MIN_BODY_CHARS, SEEN_PATH


def _uid(entry):
    """기사 고유 ID. link > id > title 순으로 해시."""
    key = entry.get("link") or entry.get("id") or entry.get("title", "")
    return hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:16]


def _clean(html):
    """RSS summary의 간단한 태그 제거."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def load_seen(path=SEEN_PATH):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen, path=SEEN_PATH):
    # 무한 성장 방지: 최근 2000개만 유지
    trimmed = list(seen)[-2000:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=0)


def _norm_title(title):
    return re.sub(r"\W+", "", (title or "").lower())[:60]


def _outlet(entry, fallback):
    """구글뉴스 아이템은 <source>에 실제 매체명(Bloomberg 등)이 들어 있음."""
    esrc = entry.get("source")
    if esrc and hasattr(esrc, "get"):
        title = (esrc.get("title") or "").strip()
        if title:
            return title
    return fallback


def collect(seen):
    """RSS에서 미열람 기사 수집 → 최신순 상위 N개. (실행 내 uid/제목 중복도 제거)"""
    items = []
    seen_uid = set()
    seen_titles = set()
    for feed in FEEDS:
        try:
            parsed = feedparser.parse(feed["url"])
        except Exception as e:
            print(f"[warn] feed 파싱 실패 {feed['name']}: {e}")
            continue
        for entry in parsed.entries:
            uid = _uid(entry)
            if uid in seen or uid in seen_uid:      # 과거 열람 + 이번 실행 내 uid 중복
                continue
            title = (entry.get("title") or "").strip()
            outlet = _outlet(entry, feed["name"])
            # 구글뉴스 제목의 " - 매체명" 꼬리 제거
            if outlet and title.endswith(f" - {outlet}"):
                title = title[: -(len(outlet) + 3)].strip()
            nt = _norm_title(title)
            if nt and nt in seen_titles:            # 같은 기사(다른 피드) 중복 제거
                continue
            seen_uid.add(uid)
            if nt:
                seen_titles.add(nt)
            items.append({
                "uid": uid,
                "market": feed.get("market", "US"),
                "source": outlet,
                "title": title,
                "link": entry.get("link", ""),
                "summary": _clean(entry.get("summary", "")),
                "published": entry.get("published_parsed"),
            })

    items.sort(key=lambda x: x["published"] or time.gmtime(0), reverse=True)
    return items[:MAX_CANDIDATES]


def fetch_body(url):
    """기사 본문 추출. 실패 시 빈 문자열."""
    if not url or trafilatura is None:
        return ""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(
            downloaded, include_comments=False, include_tables=False
        ) or ""
        return text.strip()
    except Exception as e:
        print(f"[warn] 본문 추출 실패 {url}: {e}")
        return ""


def enrich(articles):
    """각 기사에 본문 채우기(짧으면 RSS 요약으로 폴백, 토큰 절약 위해 6000자 컷)."""
    for a in articles:
        body = fetch_body(a["link"])
        if len(body) < MIN_BODY_CHARS:
            body = a["summary"]
        a["body"] = body[:6000]
    return articles
