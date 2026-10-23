"""Compact Korean email report for 3-6+ month discretionary investment research."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from html import escape

KST = timezone(timedelta(hours=9))


def e(value):
    return escape(str(value if value is not None else ""), quote=True)


def _html_item(a):
    brief = [x.strip() for x in str(a.get("brief") or "").splitlines() if x.strip()]
    title = brief[0] if brief else a.get("title", "")
    what = brief[1] if len(brief) > 1 else ""
    watch = brief[2] if len(brief) > 2 else ""
    link = str(a.get("link") or "")
    source = str(a.get("source") or "원문")
    date = ""
    if a.get("published"):
        try:
            date = datetime.fromtimestamp(calendar.timegm(a["published"]), timezone.utc).astimezone(KST).strftime("%m-%d %H:%M")
        except (TypeError, ValueError, OverflowError):
            pass
    anchor = (f"<a href='{e(link)}' style='color:#2563eb;text-decoration:none'>"
              f"{e(source)} ↗</a>") if link.startswith("https://") or link.startswith("http://") else e(source)
    return (f"<div style='padding:12px 0;border-bottom:1px solid #e5e7eb'>"
            f"<div style='font-weight:700;color:#1f2937;font-size:14px'>{e(title)}</div>"
            f"<div style='color:#374151;font-size:12px;margin-top:4px;line-height:1.6'>{e(what)}</div>"
            f"<div style='color:#6b7280;font-size:12px;margin-top:3px;line-height:1.5'>{e(watch)}</div>"
            f"<div style='font-size:11px;color:#9ca3af;margin-top:6px'>{anchor} · {e(date)} KST</div></div>")




def _candidate_metrics(c):
    detail = c.get("detail") or {}
    market = c.get("market_info") or {}
    valuation = c.get("valuation_info") or {}
    specs = [
        ("3개월", market.get("return_3m_pct"), "%"),
        ("52주 최고 대비", market.get("below_52w_high_pct"), "%"),
        ("매출 성장 YoY", detail.get("revenue_growth_yoy_pct"), "%"),
        ("영업이익률", detail.get("operating_margin_pct"), "%"),
        ("FCF 수익률", detail.get("fcf_yield_pct"), "%"),
        ("선행 PER", valuation.get("forward_pe"), "배"),
        ("EPS 성장 추정", valuation.get("expected_earnings_growth_pct"), "%"),
        ("순차입금", detail.get("net_debt_bil_usd"), "십억 USD"),
    ]
    bits = [
        f"<span style='display:inline-block;padding:3px 7px;margin:2px;background:#f3f4f6;border-radius:4px'>"
        f"{e(label)} <b>{float(value):.1f}{e(unit)}</b></span>"
        for label, value, unit in specs if isinstance(value, (int, float))
    ]
    return "<div style='font-size:11px;margin:8px 0'>" + "".join(bits) + "</div>" if bits else ""


def _community_html(community):
    data = community or {}
    parts = [
        "<h3 style='margin:20px 0 8px;font-size:16px'>💬 즐겨보는 곳의 새로운 주제</h3>",
        "<p style='font-size:11px;color:#6b7280'>공개 게시물·영상 제목 기준. 전체 본문·영상 자막 분석이 아니며 확인된 사실로 취급하지 않습니다.</p>",
    ]
    for item in (data.get("items") or [])[:7]:
        url = str(item.get("url") or "")
        if not url.startswith("https://"):
            continue
        parts.append(
            f"<div style='border-bottom:1px solid #e5e7eb;padding:7px 0;font-size:12px'>"
            f"<b>{e(item.get('source'))}</b> · <a href='{e(url)}'>{e(item.get('title'))}</a>"
            f"<div style='font-size:11px;color:#6b7280'>{e(item.get('basis'))}</div></div>"
        )
    if not data.get("items"):
        parts.append("<p style='font-size:12px'>새로 확인한 공개 제목이 없거나 접근이 제한됐습니다.</p>")
    statuses = " · ".join(e(name) + ": " + e(note)
                          for name, note in (data.get("statuses") or {}).items())
    parts.append(f"<div style='font-size:11px;color:#6b7280;margin-top:8px'>{statuses}</div>")
    return "".join(parts)


def _macro_context(snapshot):
    indicators = [
        ("VIX", "vix", ""),
        ("하이일드 스프레드", "high_yield_spread_pct", "%p"),
        ("미국 2년", "us_2y_yield_pct", "%"),
        ("미국 10년", "us_10y_yield_pct", "%"),
    ]
    texts = []
    for label, key, suffix in indicators:
        datum = (snapshot.get("macro") or {}).get(key) or {}
        value = datum.get("value")
        if isinstance(value, (float, int)):
            texts.append(f"{e(label)} <b>{float(value):.2f}{e(suffix)}</b> "
                         f"({e(str(datum.get('as_of') or '')[:10])})")
    return "<div style='margin-top:8px;font-size:11px'>" + " · ".join(texts) + "</div>" if texts else ""

def _candidate_commentary(c):
    deep = c.get("deep_dive")
    if not isinstance(deep, dict):
        return (f"<div style='font-size:12px;margin-top:4px'>기회: {e(c.get('bull_case'))}</div>"
                f"<div style='font-size:12px;margin-top:4px'>반론: {e(c.get('bear_case'))}</div>"
                f"<div style='font-size:12px;margin-top:4px'>관찰 조건: {e(c.get('entry_condition'))}</div>")
    names = (
        ("why", "투자 가설"),
        ("catalyst", "3~6개월 촉매"),
        ("bear", "반대 시나리오"),
        ("entry", "진입 검토"),
        ("exit", "가설 무효화"),
        ("alternative", "대안 비교"),
    )
    html = "<div style='font-size:11px;color:#6b7280;margin:6px 0'>AI가 관측 자료를 바탕으로 작성한 가설이며 사실 확인이 완료된 예측이 아닙니다.</div>"
    for key, title in names:
        if deep.get(key):
            html += f"<div style='font-size:12px;margin-top:5px'><b>{e(title)}:</b> {e(deep[key])}</div>"
    return html


def _candidate(c):
    tags = " · ".join(c.get("risk_tags") or [])
    status = c.get("status", "조사 후보")
    color = "#b45309" if tags else "#0369a1"
    sources = c.get("sources") or []
    source_link = (f"<a href='{e(sources[0])}' style='color:#2563eb'>자료 ↗</a>" if sources else "")
    return (f"<div style='border:1px solid #e5e7eb;border-radius:10px;padding:12px;margin:9px 0;background:#fff'>"
            f"<div style='font-size:14px;font-weight:700'>{e(c.get('name'))} · {e(c.get('ticker'))} "
            f"<span style='font-size:11px;font-weight:600;color:{color}'>{e(status)}</span></div>"
            f"<div style='font-size:11px;color:#6b7280;margin:4px 0'>근거 {e(c.get('evidence'))} · 가격 기준 {e(c.get('quote_date'))} · {source_link}</div>"
            + _candidate_metrics(c)
            + _candidate_commentary(c)
            + (f"<div style='font-size:12px;color:#b45309;margin-top:4px'>⚠️ {e(tags)}</div>" if tags else "")
            + "</div>")


def _asset_table(snapshot):
    values = snapshot.get("asset_classes") or []
    if not values:
        return "<p style='font-size:12px'>자산군 데이터 수집 실패</p>"
    heads = ["VOO", "QQQM", "RSP", "VXUS", "SHY", "IEF", "TLT", "IAU"]
    lookup = {v.get("ticker"): v for v in values}
    rows = []
    for ticker in heads:
        a = lookup.get(ticker)
        if not a:
            continue
        ret = a.get("return_3m_pct")
        rend = f"{ret:+.1f}%" if isinstance(ret, (float, int)) else "미확인"
        date = str(a.get("as_of") or "")[:10]
        rows.append(f"<tr><td style='padding:5px;border-bottom:1px solid #e5e7eb'><b>{e(ticker)}</b> {e(a.get('name'))}</td>"
                    f"<td style='padding:5px;text-align:right;border-bottom:1px solid #e5e7eb'>{e(rend)}</td>"
                    f"<td style='padding:5px;font-size:11px;color:#6b7280;border-bottom:1px solid #e5e7eb'>{e(date)}</td></tr>")
    return ("<table style='border-collapse:collapse;font-size:12px;width:100%'>"
            "<tr style='background:#f3f4f6'><th align='left' style='padding:6px'>자산</th>"
            "<th style='padding:6px'>3개월</th><th style='padding:6px'>가격 기준일</th></tr>"
            + "".join(rows) + "</table>"
            "<p style='color:#6b7280;font-size:11px'>USD 기준 ETF 가격수익률. 총수익·환율·밸류에이션·수익률 전망과 다르며, 수익률 순위는 매수 순위가 아닙니다.</p>")


def make_digest(articles, snapshot, regime, candidates, changes=None, generated_at=None, community=None):
    dt = (generated_at or datetime.now(KST)).astimezone(KST)
    day = dt.strftime("%Y-%m-%d")
    evidence = len(snapshot.get("assets") or {})
    scanned = len(snapshot.get("watchlist") or [])
    warning_count = len(snapshot.get("collection_warnings") or [])
    rate = (snapshot.get("macro") or {}).get("us_10y_yield_pct") or {}
    yield_text = f" · 미국 10년물 {float(rate['value']):.2f}%" if rate.get("value") is not None else ""
    status = f"시장 위험: {e(regime)}{e(yield_text)}"
    market_note = "버블 여부는 현재 지표만으로 확정하지 않으며 과열·신용경색·실적 하향을 구분합니다."
    start = (f"<div style='max-width:650px;margin:auto;padding:20px;background:#f9fafb;font-family:Arial,Apple SD Gothic Neo,sans-serif;color:#111827'>"
             f"<div style='font-size:21px;font-weight:800'>STOCK BRIEF <span style='color:#2563eb'>V4</span></div>"
             f"<div style='font-size:12px;color:#6b7280;margin:5px 0 14px'>"
             f"{e(day)} · 3~6개월 이상 · 주식·ETF·채권·금 · 신호는 조사 우선순위</div>"
             f"<div style='padding:13px;background:#eff6ff;border-radius:10px;font-size:12px;line-height:1.6'>"
             f"<b>{status}</b><div>{e(market_note)}</div>"
             f"<div style='color:#64748b'>분석 기업 {scanned}개 · 후보 근거 확보 {evidence}개 · 데이터 수집 경고 {warning_count}건</div>"
             + _macro_context(snapshot) + "</div>")
    picks = "<h3 style='margin:20px 0 8px;font-size:16px'>🎯 이번에 볼 투자 후보</h3>"
    if candidates:
        picks += "".join(_candidate(c) for c in candidates[:3])
    else:
        picks += "<p style='font-size:12px'>오늘은 충분한 가격·기업 데이터를 가진 후보가 없습니다. 현금 보유도 선택지입니다.</p>"
    events = "<h3 style='margin:20px 0 8px;font-size:16px'>🗞️ 꼭 알아야 할 사건</h3>"
    if articles:
        events += "".join(_html_item(a) for a in articles[:5])
    else:
        events += "<p style='font-size:12px'>신규 중요 뉴스 없음 또는 데이터 수집 제한</p>"
    assets = "<h3 style='margin:20px 0 8px;font-size:16px'>🌐 지수·채권·금 비교</h3>" + _asset_table(snapshot)
    community_section = _community_html(community)
    shifts = ""
    if changes:
        shifts = "<h3 style='margin:18px 0 8px;font-size:15px'>🔄 이전 분석과 달라진 점</h3>"
        shifts += "".join(f"<div style='font-size:12px;margin:5px 0'>{e(x)}</div>" for x in changes[:4])
    risk = ""
    if "고위험" in regime or "복합 시장 스트레스" in regime:
        risk = ("<div style='padding:10px;border-left:3px solid #d97706;background:#fffbeb;font-size:12px'>"
                "⚠️ 복합 시장 위험 신호: 현금·단기채 등 방어 대안과 인버스/풋옵션의 비용을 함께 비교할 단계."
                " 일일 재설정 레버리지·인버스 ETF는 3~6개월 기본 보유 전략으로 가정하지 않습니다.</div>")
    end = ("<div style='font-size:11px;color:#6b7280;border-top:1px solid #e5e7eb;padding-top:12px;margin-top:20px'>"
           "시장 데이터는 지연될 수 있고, 기업 추정치는 공시된 확정 실적이 아닙니다. "
           "SEC/뉴스/커뮤니티 자료 미수집 시 확인한 것으로 취급하지 않습니다. "
           "아카라이브·위폴·유튜브의 로그인 전용 콘텐츠는 자동 수집되지 않습니다. "
           "현재 보유 종목은 없는 것으로 전달받았으며 모든 매매는 직접 결정합니다."
           "</div></div>")
    return day, start + picks + events + assets + community_section + shifts + risk + end
