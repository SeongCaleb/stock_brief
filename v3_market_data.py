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
        if 0 <= (now.date() - date).days <= 120:
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
    symbols = symbols[:24]
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
        # SEC filing is supplementary. A delayed Yahoo quote and indicative
        # forward P/E OR EPS growth estimate are enough to surface an idea.
        # They are not enough for an unconditional buy recommendation.
        if pe is not None and pe <= 0:
            pe = None
        if estimates is not None and not (-80 <= estimates <= 200):
            estimates = None
        if pe is None and estimates is None:
            asset["warning"] = "판단 근거 부족: 선행 PER·EPS 성장추정 모두 없음"
            continue
        peer = asset["peer_forward_pe_median"]
        source_urls = list(asset["sources"])
        price = asset["market"]["price"]
        positives = [f"최근 확인 가격 {price:.2f} USD"]
        negatives = ["분석 기간 3~6개월 이상에도 시장 변동·환율 위험 존재"]
        if estimates is not None:
            positives.append(f"다음 회계연도 EPS 성장 추정 {estimates:.1f}% (확정 실적 아님)")
            if estimates < 0:
                negatives.append("이익 감소 예상")
        else:
            negatives.append("EPS 성장 추정치 없음")
        if pe is not None:
            positives.append(f"선행 PER {pe:.1f}배 (업체 제공 추정)")
            if peer is not None and peer > 0:
                negatives.append(f"비교기업 선행 PER 중앙값 {peer:.1f}배")
            else:
                negatives.append("동종기업과의 신뢰할 만한 가격 비교 부족")
        else:
            negatives.append("선행 PER 확인 불가")
        risk_tags = []
        if pe and peer and peer > 0 and pe / peer >= 1.5 and (estimates is None or estimates < 20):
            risk_tags.append("동종 기업 대비 고평가 주의")
        gap = asset["market"].get("ma200_gap_pct")
        r3 = asset["market"].get("return_3m_pct")
        if gap is not None and r3 is not None and gap >= 20 and r3 >= 30:
            risk_tags.append("단기 과열 가능성")
        if risk_tags:
            negatives.extend(risk_tags)
        # The labels mean strength of evidence, NOT probability of returns.
        evidence = "보통" if pe is not None and estimates is not None and peer is not None else "제한적"
        status = "매수 조건 검토" if evidence == "보통" else "조사 후보"
        if risk_tags:
            status = "가격·과열 주의"
        thesis = {
            "bull_case": "; ".join(positives) + ". 이 숫자가 실제 실적 개선으로 이어지는지 추적",
            "bear_case": "; ".join(negatives),
            "entry_condition": "다음 실적·기업 전망과 현재 가격 재확인 후 분할 진입 여부 검토; 매수 시점 확정 아님",
            "invalidation": "이익 전망 하향 또는 재무·유동성 위험 확인 시 가설 재평가",
            "source_urls": source_urls,
        }
        asset["warning"] = "과열/가치 경고: " + ", ".join(risk_tags) if risk_tags else None
        asset["candidate_status"] = status
        snapshot["assets"][symbol] = {
            "name": asset["name"],
            "sector": asset.get("sector", ""),
            "market": {
                "as_of": asset["market"]["as_of"],
                "source_url": asset["market"]["source_url"],
                "price": price,
                "return_3m_pct": r3,
                "ma200_gap_pct": gap,
            },
            # These are vendor estimates recorded at the quote date,
            # NOT claims validated or published by an SEC filing.
            "financials": {
                "as_of": asset["market"]["as_of"],
                "source_url": asset["market"]["source_url"],
                "forward_pe": pe,
                "peer_forward_pe_median": peer,
                "expected_earnings_growth_pct": estimates,
                "kind": "vendor_estimates",
            },
            "thesis": thesis,
            "risk_tags": risk_tags,
            "evidence_level": evidence,
            "candidate_status": status,
            "sec_filing": filing,
        }
    return snapshot
