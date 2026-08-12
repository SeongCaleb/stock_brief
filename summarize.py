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

    if not picks:  # 파싱 실패 시 안전 폴백: 최신 N건, 신호는 중립
        print("[warn] triage JSON 파싱 실패 → 최신 기사로 폴백")
        return [{**a, "signal": "중립"} for a in candidates[:MAX_ARTICLES]]

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
    return selected or [{**a, "signal": "중립"} for a in candidates[:MAX_ARTICLES]]


def _parse_json_array(text):
    """코드펜스/잡텍스트가 섞여도 첫 JSON 배열을 뽑아 파싱."""
    t = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\[.*\]", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return []
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
