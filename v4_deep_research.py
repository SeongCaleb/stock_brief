"""One low-cost batch Claude call for 3–6 month candidate investment hypotheses.

Uses ONLY the dated vendor metrics and titled news supplied by the pipeline.
No model free-form facts are converted into verified claims or price targets.
"""
from __future__ import annotations

import json
import re


SYSTEM = """당신은 기업별 투자 가설을 검토하는 한국어 투자 리서치 작성자입니다.
입력은 신뢰도가 서로 다른 날짜가 있는 공급업체 주가·추정 지표, 기사 제목,
공개 커뮤니티·방송 제목이다. 뉴스 제목만으로 사건이 사실이라고 확정하지 마세요.
웹검색과 최신 공시를 본 척하거나 제공되지 않은 회사 사실, 숫자, 목표주가,
수익률 예측, 행사·실적 발표 날짜를 절대 만들어내지 마세요.

목표는 3~6개월 이상 투자자의 *조건부 검토*에 필요한 가설을 만드는 것이다.
각 종목에 대해:
- why: 현재 공개된 숫자만 바탕으로 살펴볼 이유. 근거 부족하면 정량 자료 부족 표시.
- catalyst: 3~6개월 사이 확인할 실적/거시 변화 또는 촉매(미확정 사건은 '가능성').
- bear: 가장 강한 반대 가설; 기업 위험과 가격 위험을 구분.
- entry: 어떤 숫자/조건을 확인한 뒤 진입을 검토할지.
- exit: 가설이 틀렸다고 판단할 조건.
- alternative: 다른 자산 또는 지수 ETF와 비교할 이유.
모든 필드는 한국어 짧은 문장 하나(150자 이내). 비밀 데이터, 무조건 사라/팔아라,
막연한 가격예측은 금지.

반드시 다음 JSON 배열만 출력:
[{"ticker":"티커", "why":"...", "catalyst":"...", "bear":"...",
"entry":"...", "exit":"...", "alternative":"..."}]
"""


FIELDS = ("why", "catalyst", "bear", "entry", "exit", "alternative")


def research_candidates(candidates, articles, community, caller):
    """Fail open to existing quantified memo if model is unavailable."""
    if not candidates:
        return candidates
    batch = []
    for item in candidates[:3]:
        batch.append({
            "ticker": item["ticker"],
            "sector": item.get("sector"),
            "valuation": item.get("valuation_info"),
            "market": item.get("market_info"),
            "fundamentals": item.get("detail"),
            "observed_at": item.get("quote_date"),
            "risk_flags": item.get("risk_tags") or [],
        })
    context = {
        "candidates": batch,
        "mainstream_headlines": [
            {"title": a.get("title", "")[:130], "url": a.get("link", "")}
            for a in (articles or [])[:5]
        ],
        "user_favorites_unverified_titles": [
            {"source": a.get("source"), "title": a.get("title", "")[:120]}
            for a in (community or [])[:4]
        ],
    }
    try:
        raw = caller(SYSTEM, json.dumps(context, ensure_ascii=False), max_tokens=2200)
        match = re.search(r"\[[\s\S]*\]", raw)
        parsed = json.loads(match.group(0) if match else raw)
        if not isinstance(parsed, list):
            raise ValueError("analysis must be a list")
        table = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker", "")).upper()
            if ticker not in {c["ticker"] for c in candidates[:3]}:
                continue
            fields = {k: str(item.get(k) or "").strip().replace("\n", " ")[:180]
                      for k in FIELDS}
            if all(fields.values()):
                table[ticker] = fields
        for candidate in candidates:
            if candidate["ticker"] in table:
                candidate["deep_dive"] = table[candidate["ticker"]]
        return candidates
    except Exception as exc:
        print("[warn] 심층 투자 가설 분석 제외:", type(exc).__name__)
        return candidates
