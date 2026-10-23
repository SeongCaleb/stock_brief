"""Conservative research helpers for the 3-6 month Stock Brief email.

No live pricing or financial data is invented. Optional market_snapshot.json
must contain dated observations with working HTTPS source links.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

KST = timezone(timedelta(hours=9))
NOISE = (
    r"\b(?:should i|retirement savings|retire with|cd account|cd rates|"
    r"social security benefits|credit card|personal loan|how much should i save)\b",
    r"(?:은퇴자금|정기예금 추천|개인 재무 상담|신용카드 추천)",
    r"\b(?:sponsored content|advertorial|affiliate links)\b",
)
TOPICS = (
    "금리", "연준", "관세", "실적", "반도체", "채권", "환율", "국채",
    "원유", "유가", "인플레", "고용", "수출", "부채", "회계", "파산",
    "federal reserve", "treasury", "yield", "earnings", "guidance",
    "credit spread", "inflation", "semiconductor", "bond", "tariff",
    "oil", "gold", "equity", "stock", "market", "index",
)
REQUIRED_THESIS = ("bull_case", "bear_case", "entry_condition", "invalidation")


def dated_articles(items, now=None, max_age_hours=72):
    """Remove personal-finance filler and stale articles BEFORE spending AI tokens."""
    now = now or datetime.now(timezone.utc)
    result = []
    for a in items:
        title = str(a.get("title") or "")
        excerpt = str(a.get("summary") or "")
        text = (title + " " + excerpt).lower()
        if len(title.strip()) < 12 or any(re.search(p, text, re.I) for p in NOISE):
            continue
        if len(excerpt.strip()) < 35 and not any(word in text for word in TOPICS):
            continue
        pub = a.get("published")
        if not pub:
            continue
        import calendar
        try:
            age = (now.timestamp() - calendar.timegm(pub)) / 3600
        except (ValueError, OverflowError, TypeError):
            continue
        if -2 <= age <= max_age_hours:
            result.append(a)
    return result


def _fresh(entry, days, now):
    if not isinstance(entry, dict):
        return False
    url = entry.get("source_url", "")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        if parsed.hostname.lower() in ("example.com", "example.net", "example.org"):
            return False
        dt = datetime.fromisoformat(str(entry.get("as_of", "")).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return False
        delta = (now - dt.astimezone(timezone.utc)).total_seconds()
        return -86400 <= delta <= days * 86400
    except (ValueError, TypeError):
        return False


def research_snapshot(path="market_snapshot.json", now=None):
    """Assess market stress and only recommend data-backed candidates."""
    now = now or datetime.now(timezone.utc)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or data.get("example"):
        data = {}
    macro = data.get("macro") or {}
    indicators = ("vix", "high_yield_spread_pct", "above_200dma_pct")
    # Broad market breadth is NOT available from price index alone. Do not
    # substitute SPY trend for breadth or label it a full bubble diagnosis.
    if not all(_fresh(macro.get(k), 7, now) for k in indicators):
        keys = ("vix", "high_yield_spread_pct", "spy_200dma_gap_pct")
        if all(_fresh(macro.get(k), 7, now) for k in keys):
            try:
                vix = float(macro["vix"]["value"])
                spread = float(macro["high_yield_spread_pct"]["value"])
                gap = float(macro["spy_200dma_gap_pct"]["value"])
                hits = sum((vix >= 30, spread >= 5, gap <= -10))
                regime = ("복합 시장 스트레스 경계" if hits >= 2
                          else "일부 위험 신호" if hits == 1
                          else "세 가지 스트레스 기준 미충족")
                regime += " — SPY 200일선은 시장 폭 지표가 아니며 버블 판정 불가"
            except (ValueError, TypeError, KeyError):
                regime = "판단 보류 — 지표 형식 오류"
        else:
            regime = "판단 보류 — 최신 VIX·신용 스프레드·추세 자료 부족"
    else:
        try:
            vix = float(macro["vix"]["value"])
            spread = float(macro["high_yield_spread_pct"]["value"])
            breadth = float(macro["above_200dma_pct"]["value"])
            hits = sum((vix >= 30, spread >= 5, breadth <= 30))
            regime = ("고위험 경계" if hits >= 2
                      else "주의" if hits == 1 else "극단적 스트레스 조건 미충족")
            regime += " — 단기 하락 시점 예측 아님"
        except (TypeError, ValueError, KeyError):
            regime = "판단 보류 — 시장 지표 형식 오류"
    assets = data.get("assets") or {}
    candidates = []
    if not isinstance(assets, dict):
        assets = {}
    for ticker, asset in assets.items():
        if not isinstance(asset, dict):
            continue
        price = asset.get("market") or {}
        financials = asset.get("financials") or {}
        thesis = asset.get("thesis") or {}
        if not (_fresh(price, 7, now) and _fresh(financials, 30, now)):
            continue
        if financials.get("going_concern_warning") is True:
            continue
        if not all(thesis.get(k) for k in REQUIRED_THESIS):
            continue
        refs = [u for u in (thesis.get("source_urls") or [])
                if isinstance(u, str) and u.startswith("https://")
                and urlsplit(u).hostname]
        if not refs:
            continue
        try:
            market_price = float(price["price"])
        except (ValueError, TypeError, KeyError):
            continue
        if not 0 < market_price < 1e8:
            continue
        def optional_numeric(field):
            try:
                value = float(financials[field])
                return value if -1e5 < value < 1e5 else None
            except (ValueError, TypeError, KeyError):
                return None
        pe = optional_numeric("forward_pe")
        peer = optional_numeric("peer_forward_pe_median")
        growth = optional_numeric("expected_earnings_growth_pct")
        pe = pe if pe is not None and pe > 0 else None
        peer = peer if peer is not None and peer > 0 else None
        growth = growth if growth is not None and -80 <= growth <= 200 else None
        # A single verified, dated vendor dataset can surface a RESEARCH idea.
        # It cannot produce an unconditional buy or a high-confidence claim.
        if pe is None and growth is None:
            continue
        tags = [str(t)[:90] for t in asset.get("risk_tags", []) if isinstance(t, str)]
        if pe and peer and pe / peer >= 1.5 and (growth is None or growth < 20):
            if "동종 기업 대비 고평가 주의" not in tags:
                tags.append("동종 기업 대비 고평가 주의")
        evidence = "보통" if pe is not None and peer is not None and growth is not None else "제한적"
        label = "매수 조건 검토" if evidence == "보통" else "조사 후보"
        if tags:
            label = "가격·과열 주의"
        # Explicit heuristic priority, never a forecast or target price.
        score = (growth * 0.5 if growth is not None else -10)
        score -= (pe * 0.2 if pe is not None else 10)
        if pe is not None and peer is not None:
            score += max(-12, min(8, (peer - pe) * 0.5))
        score -= 12 * len(tags)
        candidates.append({
            "ticker": str(ticker).upper()[:16],
            "name": str(asset.get("name") or ticker)[:70],
            "score": round(score, 2),
            "status": label,
            "evidence": evidence,
            "risk_tags": tags,
            "quote_date": str(price.get("as_of", ""))[:10],
            "bull_case": str(thesis["bull_case"])[:300],
            "bear_case": str(thesis["bear_case"])[:300],
            "entry_condition": str(thesis["entry_condition"])[:300],
            "invalidation": str(thesis["invalidation"])[:300],
            "sources": refs[:3],
        })
    return regime, sorted(candidates, key=lambda x: -x["score"])[:3]


def research_html(regime, candidates, has_news):
    parts = [
        "<div style='border:1px solid #e5e7eb;border-radius:12px;padding:14px;background:#fff;'>",
        "<div style='font-weight:700;margin-bottom:7px;'>🌍 3~6개월 투자 리서치</div>",
        "<div><b>시장 스트레스:</b> " + escape(regime) + "</div>",
        "<div style='margin-top:8px;font-size:12px;color:#6b7280'>"
        "개별 종목의 재무위험·고평가·단기 과열은 서로 다릅니다. "
        "유효한 공식/시세 자료 없이는 안전하다고 판정하지 않습니다.</div>",
        "</div>",
        "<h3 style='font-size:15px'>🎯 관심·매수 검토 후보 (조건부)</h3>",
        "<p style='font-size:12px;color:#6b7280'>추천 탐색은 빠르게 진행하지만, 확신도는 자료 수준에 따라 구분합니다. 모두 3~6개월 이상 관찰 대상이며 확정 매수 신호는 아닙니다.</p>",
    ]
    if not candidates:
        parts.append("<p>이번에는 추천 보류 — 신선한 시세 및 최소 한 가지 가치·성장 지표가 없어 조사할 후보를 선정하지 못했습니다.</p>")
    for i, item in enumerate(candidates, 1):
        parts.append(
            "<div style='margin:12px 0;padding:12px;border:1px solid #e5e7eb;background:#fff'>"
            f"<b>{i}. {escape(item['name'])} ({escape(item['ticker'])})</b>"
            f"<p><b>{escape(item['status'])}</b> · 근거 수준: {escape(item['evidence'])}"
            f" · 가격 기준일: {escape(item['quote_date'])}</p>"
            + (f"<p style='color:#b45309'>⚠️ {escape(', '.join(item['risk_tags']))}</p>" if item["risk_tags"] else "")
            + f"<p>성장 가설: {escape(item['bull_case'])}</p>"
            f"<p>반론: {escape(item['bear_case'])}</p>"
            f"<p>진입 검토 조건: {escape(item['entry_condition'])}</p>"
            f"<p>가설 무효화: {escape(item['invalidation'])}</p>"
            + "".join(
                f"<a href='{escape(u, quote=True)}' style='margin-right:12px'>근거 {j}</a>"
                for j, u in enumerate(item["sources"], 1)
            )
            + "</div>"
        )
    if not has_news:
        parts.append("<p>오늘 선별된 새로운 중요 기사가 없습니다. 기사 수집 불가 가능성도 점검해야 합니다.</p>")
    parts.append("<div style='color:#6b7280;font-size:11px;margin-top:12px'>"
                 "현재 보유 종목 없음(사용자 제공 정보). 투자 여부와 주문은 사용자가 결정합니다. "
                 "벤더 추정치는 확정 실적이 아니며, 자료 미확보 시 판단은 보류합니다.</div>")
    return "\n".join(parts)
