"""Anthropic Messages API: (1) 중요 뉴스 선별+신호 부여, (2) 짧은 3줄 브리핑 요약."""
import json
import re

import requests

from config import (ANTHROPIC_API_KEY, ANTHROPIC_API_URL, ANTHROPIC_MODEL,
                    ANTHROPIC_VERSION, MAX_ARTICLES)

_HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": ANTHROPIC_VERSION,
    "content-type": "application/json",
}

# 신호 → 이모지
SIGNAL_EMOJI = {"강세": "📈", "약세": "📉", "주의": "⚠️", "중립": "➡️"}


def _call(system, user, max_tokens):
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    r = requests.post(ANTHROPIC_API_URL, headers=_HEADERS, json=payload, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# 1단계: 선별(triage) — 후보 중 '꼭 알아야 할' 뉴스만 고르고 방향 신호를 붙임
# ---------------------------------------------------------------------------
TRIAGE_SYSTEM = """당신은 미국·한국 증시 뉴스 데스크 편집자입니다.
아래 후보 기사 목록(미국·한국 혼재)에서 '개인 투자자가 오늘 꼭 알아야 할' 시장 중요 뉴스만 골라주세요.

선정 기준:
- 시장을 움직이거나, 주요 종목·섹터 전망에 영향을 주거나, 거시(연준·금리·고용·물가·유가·환율) 이슈인 기사를 우선.
- 미국·한국 양쪽을 균형 있게 고려하되, 중요도가 우선. 한쪽에 중요한 게 없으면 다른 쪽에서 더 골라도 됨.
- 다음은 제외: 개인 재무 상담·조언 칼럼(예: 예금·CD·은퇴자금 고민), 내용 없는 자동 실적 블러브("X posts earnings" 류), 낚시성 리스티클, 광고성, 특정 무명 소형주 단순 소개.

각 선정 기사에 '뉴스가 시사하는 방향' 신호를 붙이세요 (기사 내용 근거, 매수·매도 지시가 아님):
- "강세": 긍정적 전망·호실적·상승 촉매
- "약세": 부정적·리스크·하락 촉매 (빠르게 대응·경계할 사안)
- "주의": 불확실·변동성·판단 보류
- "중립": 참고 수준

최대 {n}건. 중요한 게 그보다 적으면 적게 골라도 됩니다. 최신·중요도 순으로 정렬.

출력은 JSON 배열만. 코드펜스·설명 금지:
[{{"index": 후보번호(정수), "signal": "강세|약세|주의|중립", "reason": "한 줄 근거"}}]
"""


def triage(candidates):
    """후보 리스트 → 선별된 기사 리스트(각 항목에 signal 추가)."""
    if not candidates:
        return []
    lines = []
    for i, a in enumerate(candidates):
        snippet = (a.get("summary") or "")[:200]
        flag = "🇰🇷" if a.get("market") == "KR" else "🇺🇸"
        lines.append(f"{i}. {flag} [{a['source']}] {a['title']} — {snippet}")
    user = "후보 기사:\n" + "\n".join(lines)
    system = TRIAGE_SYSTEM.format(n=MAX_ARTICLES)

    raw = _call(system, user, max_tokens=1200)
    picks = _parse_json_array(raw)

    if not picks:
        print("[warn] triage JSON 파싱 실패 → 핵심 시장 이벤트 우선 휴리스틱으로 폴백")
        return _fallback_select(candidates)

    selected = []
    for p in picks[:MAX_ARTICLES]:
        try:
            idx = int(p["index"])
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= idx < len(candidates):
            art = dict(candidates[idx])
            sig = str(p.get("signal", "중립")).strip()
            art["signal"] = sig if sig in SIGNAL_EMOJI else "중립"
            art["signal_reason"] = str(p.get("reason", "")).strip()
            selected.append(art)
    return selected or _fallback_select(candidates)


# A fallback is *not* just "newest first": that can accidentally prioritize
# savings advice, marketing, or insignificant company updates.
MAJOR_EVENTS = (
    ("연준", 6), ("fomc", 7), ("federal reserve", 6), ("금리 결정", 6),
    ("central bank", 4), ("국채", 4), ("treasury yield", 4),
    ("채권", 2), ("신용 스프레드", 7), ("credit spread", 7),
    ("디폴트", 7), ("default risk", 7), ("파산", 7), ("bankruptcy", 7),
    ("물가", 4), ("inflation", 4), ("고용", 3), ("jobs report", 4),
    ("실적 전망", 5), ("earnings guidance", 5), ("revenue forecast", 4),
    ("실적", 2), ("earnings", 2), ("ai 투자", 3), ("tariff", 4),
    ("관세", 4), ("유가", 4), ("oil prices", 4), ("환율", 3), ("달러", 2),
    ("geopolitic", 3), ("무역", 3), ("코스피", 3), ("nasdaq", 3),
    ("s&p 500", 3), ("시장 급락", 4), ("selloff", 4),
    ("반도체", 2), ("semiconductor", 2), ("금융 규제", 3),
)
FILLER_TERMS = (
    "should i", "how much do i", "credit card rewards", "retirement savings",
    "best stocks to buy now", "millionaire", "what to do with", "analyst says buy",
    "posts earnings", "reports earnings", "earnings update",
    "은퇴자금", "예금 추천", "광고", "단독 추천", "클릭하세요",
)


def _fallback_select(candidates):
    ranked = []
    for index, article in enumerate(candidates):
        title = str(article.get("title") or "").lower()
        detail = str(article.get("summary") or "").lower()[:250]
        if any(w in title for w in FILLER_TERMS):
            continue
        score = sum(weight for term, weight in MAJOR_EVENTS if term in title)
        # Secondary context matters, but a long generic snippet cannot dominate.
        score += sum(min(2, weight // 3) for term, weight in MAJOR_EVENTS
                     if term in detail and term not in title)
        if article.get("source", "").startswith("세이브티커"):
            score += 1  # editorial preference, never an automatic "important" pass
        if score >= 2:
            ranked.append((score, -index, article))
    ranked.sort(key=lambda x: (-x[0], -x[1]))
    return [
        {**article, "signal": "주의", "signal_reason": "AI 선별 실패: 주요 시장 사건 키워드 기반 임시 분류"}
        for _, _, article in ranked[:MAX_ARTICLES]
    ]


def _parse_json_array(text):
    """Find a complete array with JSONDecoder instead of a greedy regex."""
    if not isinstance(text, str):
        return []
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\[", text):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
            if isinstance(obj, list):
                return obj
        except (ValueError, TypeError):
            continue
    return []


# ---------------------------------------------------------------------------
# 2단계: 짧은 3줄 브리핑
# ---------------------------------------------------------------------------
BRIEF_SYSTEM = """당신은 미국·한국 증시 뉴스를 아주 간결하게 정리하는 에디터입니다.
영어 기사는 한국어로 옮기고, 한국어 기사는 그대로 한국어로, 정확히 아래 3줄 구조로만 요약하세요.

{신호이모지} {신호} · {한 줄 헤드라인 — 반드시 한국어}
{핵심 요약 2문장 이내 — 무슨 일이고 왜 중요한지}
🎯 섹터: {관련 섹터} | 종목: {티커·기업 1~4개, 없으면 '해당 없음'} | 포인트: {지켜볼 것 한 줄}

규칙:
- 헤드라인·요약 모두 반드시 한국어로 작성 (영문 원제 그대로 쓰지 말 것).
- 함축적으로. 군더더기·중복·상투어 금지. 3줄을 넘기지 말 것.
- 기사에 없는 수치·사실은 지어내지 말 것.
- 매수·매도·목표주가를 단정하지 말 것. 신호는 '뉴스가 시사하는 방향'일 뿐.
- 신호 이모지 규칙: 강세 📈, 약세 📉, 주의 ⚠️, 중립 ➡️. 주어진 신호를 그대로 사용.
- 마크다운(#, *, **) 금지.
"""


def headline_of(brief_text):
    """브리핑 첫 줄에서 '· ' 뒤의 한글 헤드라인만 추출 (상단 목록용)."""
    for raw in brief_text.splitlines():
        line = raw.strip()
        if line.startswith(tuple(SIGNAL_EMOJI.values())) and "·" in line:
            return line.split("·", 1)[1].strip()
    return None


def summarize(article, timeout=120):
    signal = article.get("signal", "중립")
    emoji = SIGNAL_EMOJI.get(signal, "➡️")
    user = (
        f"이 기사의 신호: {signal} ({emoji}) — 이 신호를 그대로 사용하세요.\n"
        f"[출처] {article['source']}\n"
        f"[제목] {article['title']}\n"
        f"[본문]\n{article.get('body') or article.get('summary', '')}\n"
    )
    return _call(BRIEF_SYSTEM, user, max_tokens=600)
