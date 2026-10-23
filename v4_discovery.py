"""Broad, rotating, sector-neutral idea discovery and small hypothesis ledger.

The scan rotates; it is not a complete global market or a guaranteed ranking.
All financial observations come from v3_market_data and keep their as-of dates.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

SECTORS = {
    "기술": ("MSFT", "NVDA", "ORCL", "ADBE", "CRM"),
    "통신": ("GOOGL", "META", "NFLX", "TMUS", "DIS"),
    "경기소비재": ("AMZN", "TSLA", "HD", "MCD", "BKNG"),
    "필수소비재": ("COST", "PG", "KO", "WMT", "PEP"),
    "헬스케어": ("JNJ", "UNH", "ABBV", "LLY", "ISRG"),
    "금융": ("JPM", "V", "BRK-B", "GS", "BLK"),
    "산업재": ("CAT", "GE", "HON", "DE", "ETN"),
    "에너지": ("XOM", "CVX", "SLB", "COP", "EOG"),
    "소재": ("LIN", "NEM", "FCX", "SHW", "APD"),
    "유틸리티": ("NEE", "DUK", "SO", "CEG", "VST"),
    "부동산": ("PLD", "AMT", "EQIX", "O", "WELL"),
}
NEWS_ALIASES = {
    "NVDA": ("nvidia", "엔비디아"),
    "MSFT": ("microsoft", "마이크로소프트"),
    "AAPL": ("apple", "애플"),
    "GOOGL": ("alphabet", "google", "알파벳", "구글"),
    "AMZN": ("amazon", "아마존"),
    "META": ("meta platforms", "메타 플랫폼스"),
    "TSLA": ("tesla", "테슬라"),
    "AVGO": ("broadcom", "브로드컴"),
    "AMD": ("advanced micro devices", "amd", "에이엠디"),
    "INTC": ("intel", "인텔"),
    "JPM": ("jpmorgan", "jp morgan", "제이피모건"),
    "V": ("visa inc", "비자 카드"),
    "XOM": ("exxonmobil", "엑슨모빌"),
    "LLY": ("eli lilly", "일라이 릴리"),
    "PFE": ("pfizer", "화이자"),
    "PLTR": ("palantir", "팔란티어"),
    "NEM": ("newmont", "뉴몬트"),
    "CEG": ("constellation energy", "컨스텔레이션 에너지"),
    "TSM": ("taiwan semiconductor", "tsmc", "대만 반도체"),
}
CASH_TAG = re.compile(r"(?<![A-Z0-9])\$([A-Z]{2,5})(?![A-Z0-9])")
EXCHANGE_TAG = re.compile(r"\b(?:NASDAQ|NYSE|AMEX)\s*:\s*([A-Z]{2,5})\b", re.I)
STOPWORDS = {"THE", "ETF", "FED", "USA", "AI", "CEO", "GDP", "NYSE", "NASDAQ"}
TRACKING_PATH = "v4_thesis_history.json"


def identify_news_tickers(articles):
    """Only explicit exchange/cashtag symbols or clear company-name aliases."""
    results = []
    for article in articles:
        text = (" ".join(str(article.get(k) or "") for k in ("title", "summary"))).lower()
        for ticker, aliases in NEWS_ALIASES.items():
            if ticker not in results and any(a in text for a in aliases):
                results.append(ticker)
        upper = text.upper()
        for ticker in CASH_TAG.findall(upper) + EXCHANGE_TAG.findall(upper):
            if ticker not in STOPWORDS and ticker not in results:
                results.append(ticker)
    return results[:8]


def discovery_universe(articles, on_day=None, previous=None, extra=None, limit=18):
    """Cover every sector before news and prior picks, rotating a different slice daily."""
    on_day = on_day or datetime.now(timezone.utc).date()
    offset = on_day.toordinal()
    pool = []
    def add(symbol):
        symbol = str(symbol).strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,7}", symbol) and symbol not in pool:
            pool.append(symbol)
    for i, tickers in enumerate(SECTORS.values()):
        add(tickers[(offset + i) % len(tickers)])
    for symbol in (previous or [])[:3]:
        add(symbol)
    for symbol in identify_news_tickers(articles)[:4]:
        add(symbol)
    if isinstance(extra, str):
        extra = extra.split(",")
    for symbol in extra or []:
        add(symbol)
    return pool[:max(11, min(24, int(limit)))]


def _tokens(title):
    s = re.sub(r"[^0-9a-z가-힣]+", " ", str(title).lower())
    stop = {"stock", "stocks", "market", "markets", "shares", "news", "증시", "주가", "시장", "오늘", "미국"}
    return {x for x in s.split() if len(x) > 2 and x not in stop}


def unique_events(articles):
    """Suppress nearly-identical syndicated headlines, not merely shared themes."""
    unique = []
    existing = []
    for item in articles:
        tokens = _tokens(item.get("title"))
        repeated = any(
            len(tokens & prior) >= 3 and (len(tokens & prior) / max(1, len(tokens | prior))) >= 0.57
            for prior in existing
        )
        if not repeated:
            unique.append(item)
            existing.append(tokens)
    return unique


def load_tracking(path=TRACKING_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def tracking_changes(snapshot, old):
    """Avoid claiming predictive performance: compare observed changes, not outcomes."""
    prior = old.get("latest", {}) if isinstance(old, dict) else {}
    changes = []
    for ticker, item in (snapshot.get("assets") or {}).items():
        prev = prior.get(ticker) or {}
        price = (item.get("market") or {}).get("price")
        if prev.get("price") and price is not None:
            try:
                delta = 100 * (float(price) / float(prev["price"]) - 1)
                if abs(delta) >= 3:
                    changes.append(f"{ticker}: 직전 관찰가 대비 {delta:+.1f}% (성과 검증 아님)")
            except (ValueError, TypeError, ZeroDivisionError):
                pass
    return changes[:4]


def next_tracking(snapshot, old, run_date=None):
    run_date = run_date or datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    latest = {}
    for ticker, item in (snapshot.get("assets") or {}).items():
        latest[ticker] = {
            "date": run_date,
            "price": item.get("market", {}).get("price"),
            "forward_pe": item.get("financials", {}).get("forward_pe"),
            "growth_estimate_pct": item.get("financials", {}).get("expected_earnings_growth_pct"),
            "source": item.get("market", {}).get("source_url"),
        }
    # Keep the previous data for tickers not sampled today, but for max 120.
    prev = old.get("latest", {}) if isinstance(old, dict) else {}
    combined = {**prev, **latest}
    return {"latest": dict(list(combined.items())[-120:]),
            "last_sent_date": run_date}


def diversify_candidates(candidates, count=3):
    """Prefer distinct reported vendor sectors, but do not invent sector labels."""
    chosen, sectors = [], set()
    for candidate in candidates:
        sector = candidate.get("sector") or "기타"
        if sector in sectors and sector != "기타":
            continue
        chosen.append(candidate)
        sectors.add(sector)
        if len(chosen) >= count:
            return chosen
    for candidate in candidates:
        if candidate not in chosen:
            chosen.append(candidate)
            if len(chosen) >= count:
                break
    return chosen
