"""Live dated market/valuation observations for Stock Brief v3.

FRED's public CSV exports provide macro observations; yfinance provides delayed
market prices and indicative vendor fundamentals. Neither is guaranteed to be
real time. Optional SEC filing confirmation requires an identifying User-Agent.
Source failures are isolated. Missing data never becomes a recommendation.
"""
from __future__ import annotations

import csv
import io
import math
import os
from datetime import datetime, timedelta, timezone
from statistics import median
from urllib.parse import quote

import requests

FRED = {
    "vix": "VIXCLS",
    "high_yield_spread_pct": "BAMLH0A0HYM2",
    "us_10y_yield_pct": "DGS10",
    "us_2y_yield_pct": "DGS2",
}
# Representative vehicles, NOT investment recommendations.
BENCHMARKS = {
    "VOO": ("미국 S&P 500", "미국 대형주"),
    "QQQM": ("나스닥 100", "미국 성장주"),
    "RSP": ("S&P 500 동일가중", "미국 대형주 분산"),
    "VXUS": ("미국 외 주식", "글로벌 분산"),
    "SHY": ("미국 단기국채", "방어·금리"),
    "IEF": ("미국 중기국채", "금리 민감"),
    "TLT": ("미국 장기국채", "높은 듀레이션 위험"),
    "IAU": ("금 현물 연동", "금·환율 위험"),
}
# Small, configurable exploratory universe. It is NOT the whole stock market.
DEFAULT_WATCHLIST = "BRK-B,JNJ,V,MSFT,GOOGL,XOM"
PEERS = {
    "BRK-B": ("JPM", "TRV"),
    "JNJ": ("MRK", "ABBV"),
    "V": ("MA", "AXP"),
    "MSFT": ("ORCL", "GOOGL"),
    "GOOGL": ("META", "MSFT"),
    "XOM": ("CVX", "COP"),
}
VALID_SYMBOL = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^=")


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _observed(value, date, source):
    return {"value": round(float(value), 4),
            "as_of": date.isoformat() + "T00:00:00+00:00",
            "source_url": source}


def _get_csv_latest(series, session, now):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    resp = session.get(url, params={"id": series, "cosd": (now.date() - timedelta(days=60)).isoformat()}, timeout=18)
    resp.raise_for_status()
    rows = csv.DictReader(io.StringIO(resp.text))
    dates = []
    for row in rows:
        try:
            date = datetime.strptime(row.get("observation_date") or row.get("DATE"), "%Y-%m-%d").date()
            val = _number(row[series])
            if val is not None and date <= now.date():
                dates.append((date, val))
        except (TypeError, ValueError, KeyError):
            continue
    if not dates:
        raise ValueError("no observations")
    date, val = max(dates)
    return _observed(val, date, f"https://fred.stlouisfed.org/series/{series}")


def _history(yf, symbol, now):
    tick = yf.Ticker(symbol)
    frame = tick.history(period="18mo", interval="1d", auto_adjust=True, timeout=12)
    if frame is None or frame.empty or "Close" not in frame:
        raise ValueError("missing price history")
    close = frame["Close"].dropna()
    if len(close) < 130:
        raise ValueError("insufficient daily price history")
    last_date = close.index[-1].date()
    if (now.date() - last_date).days > 7:
        raise ValueError("stale market price")
    vals = [float(x) for x in close]
    price = _number(vals[-1])
    if not price or price <= 0:
        raise ValueError("invalid closing price")
    def ret(days):
        return round((vals[-1] / vals[-min(len(vals),days+1)] - 1) * 100, 2) if len(vals) > days else None
    ma200 = sum(vals[-200:]) / 200 if len(vals) >= 200 else None
    gap = (price / ma200 - 1) * 100 if ma200 else None
    return tick, {
        "as_of": last_date.isoformat() + "T00:00:00+00:00",
        "source_url": "https://finance.yahoo.com/quote/" + quote(symbol, safe=""),
        "price": round(price, 4),
        "return_3m_pct": ret(63),
        "return_6m_pct": ret(126),
        "ma200_gap_pct": round(gap, 2) if gap is not None else None,
    }


def _safe_info(ticker):
    try:
        info = ticker.get_info()
        return info if isinstance(info, dict) else {}
    except Exception as exc:
        print("[warn] vendor fundamentals unavailable:", type(exc).__name__)
        return {}


def _future_growth(ticker):
    """Next fiscal year's *estimated* EPS growth; never substitute trailing earnings."""
    try:
        estimates = ticker.earnings_estimate
        if estimates is None or estimates.empty or "+1y" not in estimates.index:
            return None
        result = _number(estimates.loc["+1y", "growth"])
        return 100 * result if result is not None else None
    except Exception:
        return None


def _filings_index(session, user_agent):
    resp = session.get("https://www.sec.gov/files/company_tickers.json",
                       headers={"User-Agent": user_agent}, timeout=20)
    resp.raise_for_status()
    items = resp.json()
    return {
        str(v["ticker"]).upper().replace(".", "-"):
        int(v["cik_str"])
        for v in items.values() if isinstance(v, dict) and v.get("ticker")
    }


def _recent_sec_filing(session, cik, user_agent, now):
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    response = session.get(url, headers={"User-Agent": user_agent}, timeout=20)
    response.raise_for_status()
    rec = response.json().get("filings", {}).get("recent", {})
    filings = zip(rec.get("form", []), rec.get("filingDate", []),
                  rec.get("accessionNumber", []), rec.get("primaryDocument", []))
    for form, d, accession, document in filings:
        if form not in ("10-K", "10-Q"):
            continue
        date = datetime.strptime(d, "%Y-%m-%d").date()
        if 0 <= (now.date() - date).days <= 160:
            link = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
            return {"as_of": d, "source_url": link, "form": form}
    return None


def collect_snapshot(now=None, session=None, finance=None, watchlist=None):
    """Produce snapshot compatible with research_snapshot; never write to tracked files."""
    now = now or datetime.now(timezone.utc)
    session = session or requests.Session()
    if finance is None:
        import yfinance as finance
    snapshot = {"generated_at": now.isoformat(), "macro": {}, "assets": {},
                "asset_classes": [], "watchlist": [], "collection_warnings": [],
                "providers": {"macro": "FRED dated CSV", "market": "Yahoo Finance via yfinance",
                              "filings": "SEC optional"}}
    warnings = snapshot["collection_warnings"]
    for key, series in FRED.items():
        try:
            snapshot["macro"][key] = _get_csv_latest(series, session, now)
        except Exception as exc:
            warnings.append(f"FRED {series}: {type(exc).__name__}")
    quote_cache = {}
    def get_quote(symbol):
        if symbol not in quote_cache:
            quote_cache[symbol] = _history(finance, symbol, now)
        return quote_cache[symbol]
    try:
        _, spy = get_quote("SPY")
        if spy.get("ma200_gap_pct") is not None:
            snapshot["macro"]["spy_200dma_gap_pct"] = _observed(
                spy["ma200_gap_pct"], datetime.fromisoformat(spy["as_of"]).date(),
                spy["source_url"])
    except Exception as exc:
        warnings.append("SPY trend: " + type(exc).__name__)
    for ticker, (name, category) in BENCHMARKS.items():
        try:
            _, quote_data = get_quote(ticker)
            snapshot["asset_classes"].append(
                {"ticker": ticker, "name": name, "category": category,
                 **quote_data})
        except Exception as exc:
            warnings.append(f"{ticker} market: {type(exc).__name__}")
    universe = watchlist
    if universe is None:
        universe = os.getenv("STOCK_WATCHLIST", DEFAULT_WATCHLIST)
    if isinstance(universe, str):
        universe = universe.split(",")
    symbols = []
    for item in universe:
        item = str(item).strip().upper()
        if item and item not in symbols and all(c in VALID_SYMBOL for c in item):
            symbols.append(item)
    symbols = symbols[:12]
    sec_header = os.getenv("SEC_USER_AGENT", "").strip()
    ciks = {}
    if sec_header and "@" in sec_header:
        try:
            ciks = _filings_index(session, sec_header)
        except Exception as exc:
            warnings.append("SEC ticker list: " + type(exc).__name__)
    for symbol in symbols:
        try:
            tick, market = get_quote(symbol)
        except Exception as exc:
            warnings.append(f"{symbol} price: {type(exc).__name__}")
            continue
        info = _safe_info(tick)
        forward_pe = _number(info.get("forwardPE"))
        estimates = _future_growth(tick)
        sector = str(info.get("sector") or "")
        asset = {"ticker": symbol, "name": str(info.get("shortName") or symbol),
                 "sector": sector, "market": market,
                 "forward_pe": forward_pe,
                 "expected_earnings_growth_pct": round(estimates, 2) if estimates is not None else None,
                 "warning": None}
        sources = [market["source_url"]]
        if ciks.get(symbol):
            try:
                filing = _recent_sec_filing(session, ciks[symbol], sec_header, now)
                if filing:
                    asset["filing"] = filing
                    sources.append(filing["source_url"])
            except Exception as exc:
                warnings.append(f"{symbol} SEC: {type(exc).__name__}")
        asset["sources"] = sources
        snapshot["watchlist"].append(asset)
    # Peer multiples from distinct listed peers; representative, not sector truth.
    for asset in snapshot["watchlist"]:
        symbol = asset["ticker"]
        estimates = asset["expected_earnings_growth_pct"]
        pe = asset["forward_pe"]
        filing = asset.get("filing")
        peer_pes = []
        for peer in PEERS.get(symbol, ()):
            try:
                ptick, _ = get_quote(peer)
                pi = _safe_info(ptick)
                peerpe = _number(pi.get("forwardPE"))
                if peerpe and peerpe > 0:
                    peer_pes.append(peerpe)
            except Exception:
                continue
        asset["peer_forward_pe_median"] = round(median(peer_pes), 2) if len(peer_pes) >= 2 else None
        if (not filing or pe is None or pe <= 0 or estimates is None
                or asset["peer_forward_pe_median"] is None):
            asset["warning"] = "조건부 추천 자료 부족: SEC 공시·선행 PER·익년도 EPS 성장추정·피어 비교"
            continue
        if not (-50 <= estimates <= 150):
            asset["warning"] = "성장률 추정이 비정상적이어서 보류"
            continue
        # An explicit falsifiable research hypothesis; NOT a price forecast.
        peer = asset["peer_forward_pe_median"]
        ticker = asset["ticker"]
        thesis = {
            "bull_case": f"익년도 EPS 성장률 컨센서스 {estimates:.1f}%; 가격 {market['price']:.2f}가 아닌 실제 실적 실현을 추적",
            "bear_case": f"선행 PER {pe:.1f}배, 비교 기업 중앙값 {peer:.1f}배; 전망 하향·금리 상승 시 하락 위험",
            "entry_condition": "다음 분기 공시·이익추정 재확인, 가격 급등·시장 스트레스 확대가 없는지 확인 후 검토",
            "invalidation": "다음 실적 발표에서 EPS 성장 가설 훼손, 회계 위험 또는 신규 유동성 문제 확인",
            "source_urls": asset["sources"],
        }
        snapshot["assets"][ticker] = {
            "name": asset["name"], "market": {
                "as_of": asset["market"]["as_of"],
                "source_url": asset["market"]["source_url"],
                "price": asset["market"]["price"],
            },
            "financials": {
                "as_of": filing["as_of"] + "T00:00:00+00:00",
                "source_url": filing["source_url"],
                "forward_pe": pe,
                "peer_forward_pe_median": peer,
                "expected_earnings_growth_pct": estimates,
            },
            "thesis": thesis,
        }
    return snapshot
