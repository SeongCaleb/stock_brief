"""Stock Brief V5 report: decisions before news, all model assumptions explicit."""
from html import escape
from v4_email import _html_item, _asset_table, _community_html
from v5_decision import ASSET_NAMES

def e(x):
    return escape(str(x if x is not None else ""), quote=True)

def n(x, unit=""):
    try:
        return f"{float(x):.1f}{unit}"
    except (TypeError, ValueError):
        return "자료 없음"

def box(text):
    return "<div style='border:1px solid #e2e8f0;border-radius:10px;background:white;padding:13px;margin:9px 0'>" + text + "</div>"

def candidate_html(c, i):
    m = c.get("market_info") or {}
    v = c.get("valuation_info") or {}
    d = c.get("detail") or {}
    header = (f"<b>{i}. {e(c.get('name'))} ({e(c.get('ticker'))}) · {e(c.get('action_v5'))}</b>"
        f"<div style='font-size:11px;color:#64748b'>점수 {e(c.get('score_v5'))}/100 · "
        f"근거 {e(c.get('data_reliability'))} · 가설 확신 {e(c.get('thesis_confidence'))}"
        f" · 가격 매력도 {e(c.get('price_attractiveness'))} · {e(c.get('quote_date'))}</div>"
        f"<div style='font-size:12px;margin:7px 0'>현재 가격 USD {n(m.get('price'))} · "
        f"선행 P/E {n(v.get('forward_pe'),'배')} · 추정 EPS 성장 {n(v.get('expected_earnings_growth_pct'),'%')} · "
        f"FCF 수익률 {n(d.get('fcf_yield_pct'),'%')} · 3개월 주가 {n(m.get('return_3m_pct'),'%')}</div>")
    deep = c.get("deep_dive") or {}
    text = "".join(
        f"<div style='font-size:12px;margin:4px 0'><b>{e(name)}:</b> {e(value)}</div>"
        for name, value in [
            ("투자 가설", deep.get("why") or c.get("bull_case")),
            ("향후 3~6개월 촉매", deep.get("catalyst")),
            ("반대 시나리오", deep.get("bear") or c.get("bear_case")),
            ("진입 확인", deep.get("entry") or c.get("entry_condition")),
            ("가설 무효화", deep.get("exit") or c.get("invalidation")),
            ("대안 자산", deep.get("alternative") or "VOO·QQQM·단기채와 비교 필요")
        ] if value)
    model = c.get("scenario_v5")
    if model:
        cases = "".join(
            "<td style='border:1px solid #e2e8f0;padding:5px;text-align:center'>"
            + e(label) + "<br><b>USD " + e(model["cases"][key]["price"]) + "</b>"
            + "<br><span style='font-size:10px'>EPS " + e(model["cases"][key]["eps_revision_pct"])
            + "%, P/E " + e(model["cases"][key]["pe_change_pct"]) + "%</span></td>"
            for key,label in (("bear","하락"),("base","기본"),("bull","상승"))
        )
        zone = model.get("peer_entry_zone")
        zone_note = ("피어 P/E 기반 관찰 구간 USD " + str(zone[0]) + " ~ " + str(zone[1])
                     if zone else "가격 구간 판단 보류(피어 자료 부족)")
        text += ("<div style='font-size:11px;margin-top:8px'><b>3~6개월 가격 민감도</b></div>"
                 "<table style='border-collapse:collapse;width:100%;font-size:11px'><tr>"
                 + cases + "</tr></table>"
                 "<div style='font-size:11px;color:#64748b'>"
                 + e(zone_note) + ". EPS 수정과 P/E 재평가의 기계적 가정이며 목표가·적정가 아님.</div>")
    else:
        text += "<div style='font-size:11px'>가격 시나리오 보류: 현재가·P/E 자료 부족</div>"
    flags = c.get("risk_tags") or []
    if flags:
        text += f"<div style='font-size:11px;color:#b45309'>위험: {e(', '.join(flags))}</div>"
    return box(header+text)

def render_v5(news, snapshot, market, alloc, candidates, all_decisions,
              community, performance, changes, generated_at):
    day = generated_at.strftime("%Y-%m-%d")
    root = ("<div style='max-width:680px;margin:auto;background:#f8fafc;padding:18px;"
            "font-family:Arial,Malgun Gothic,sans-serif;color:#0f172a'>"
            "<div style='font-size:22px;font-weight:800'>STOCK BRIEF V5</div>"
            f"<div style='font-size:11px;color:#64748b'>{e(day)} · 3~6개월 이상 · 현재 미보유</div>"
            "<h3>오늘의 투자 결론</h3>"
            + box(f"<b>{e(market.get('label'))}</b><div style='font-size:12px'>"
                  + e(" · ".join(market.get("reasons") or []))
                  + "</div><div style='font-size:11px;color:#64748b'>"
                  + e(market.get("note")) + "</div>")
            + box("<b>오늘의 행동:</b> " + (e(" / ".join(
                    str(c["ticker"]) + " " + str(c["action_v5"]) for c in candidates
                )) or "후보 추천 보류")
                  + "<div style='font-size:11px'>조건 충족 시에만 계획 포지션의 일부를 검토하고 "
                    "손실 한도를 먼저 정합니다. 자동 매매 없음.</div>")
            + "<h3>① 시장별 모델 자산 배분</h3>")
    weights = "".join(
        "<tr><td style='padding:5px'>" + e(ASSET_NAMES[k]) + "</td>"
        + "<td align='right'><b>" + str(v) + "%</b></td></tr>"
        for k,v in alloc["weights"].items())
    root += box(f"<div style='font-size:12px'>{e(alloc['status'])}</div>"
                "<div style='font-size:11px;color:#64748b'>위험 성향 및 필요 현금을 파악하지 않은 예시 비중으로, "
                "사용자에게 개인화된 매수 비중이 아닙니다.</div>"
                "<table style='width:100%;font-size:12px'>" + weights + "</table>")
    root += "<h3>② 매수·대기·제외 판단과 진입 조건</h3>"
    root += "".join(candidate_html(c, i) for i,c in enumerate(candidates, 1)) if candidates else box("이번에는 후보 추천 보류")
    root += "<h3>③ 중요 뉴스와 주가 선반영 여부</h3>"
    if news:
        for a in news[:5]:
            root += _html_item(a)
            root += "<div style='font-size:11px;color:#64748b'>수혜 기업, 실적 반영 규모 및 주가 선반영 여부는 아직 정량 확인되지 않았습니다.</div>"
    else:
        root += "<p style='font-size:12px'>새로운 중요 기사 없음 또는 접근 제한</p>"
    root += "<h3>④ 시장 위험·대체 자산·기회비용</h3>"
    root += box("추가 관찰: " + e(market.get("missing"))
                + "<div style='font-size:11px'>시장 상승 종목 비중과 광범위한 이익 전망 변경은 "
                "직접 측정되지 않아 버블 여부를 단정하지 않습니다.</div>")
    root += _asset_table(snapshot)
    root += "<h3>⑤ 이전 추천과 추천 보류 판단 추적</h3>"
    if not performance:
        root += "<p style='font-size:12px'>V5 판단 기록을 축적 중으로 첫 실행에서는 성과 평가가 없습니다.</p>"
    for p in performance[:8]:
        excess = p.get("excess_pct")
        supplement = " · VOO 대비 " + str(excess) + "%p" if excess is not None else ""
        root += (f"<div style='font-size:12px'>{e(p['ticker'])} · {e(p.get('original_decision'))}"
                 f" · 가격 변화 {p['price_return_pct']:+.1f}%" + e(supplement) + "</div>")
    for message in changes[:6]:
        root += f"<div style='font-size:12px;color:#b45309'>판단 변경: {e(message)}</div>"
    root += "<p style='font-size:11px'>가격 변화는 배당·환율·거래 비용과 실제 보유 여부를 제외한 관찰치입니다.</p>"
    root += "<h3>⑥ 다음 투자 판단 변경 조건</h3>"
    root += box("분기 실적·EPS 전망 변화, 금리 결정, 고용·물가, 신용 스프레드."
                "<div style='font-size:11px'>공식 이벤트 일정은 미연동으로 날짜를 추측하지 않습니다.</div>")
    root += _community_html(community)
    root += ("<p style='border-top:1px solid #cbd5e1;font-size:11px;color:#64748b;padding-top:12px'>"
             "시세는 지연될 수 있고 PER/EPS는 공급업체의 추정치입니다. 자료 신뢰와 향후 수익 가능성은 다릅니다. "
             "모델 배분·민감도 가격은 개인별 투자 지시가 아닙니다.</p></div>")
    return day, root
