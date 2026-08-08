"""Anthropic Messages API로 기사 1건을 Axios 'Smart Brevity' 한국어 블록으로 요약 (관심 섹터·종목 포함)."""
import requests

from config import ANTHROPIC_API_KEY, ANTHROPIC_API_URL, ANTHROPIC_MODEL, ANTHROPIC_VERSION

SYSTEM = """당신은 미국 증시 뉴스 요약 에디터입니다.
영어 기사를 한국어로 옮겨 Axios 'Smart Brevity' 스타일 다이제스트로 재구성합니다.
아래 섹션 순서와 형식을 정확히 지키세요.

[적절한 이모지] {한 줄 헤드라인 — 기사의 핵심 결론}

{리드: 이 사안이 무엇이고 왜 벌어졌는지 담은 2~3문장. 구체적으로 쓸 것.}

⚖️ 중요한 이유: {왜 중요한지 1~2문장 요지}
- {근거·디테일 문장 2~4개. 각 항목은 완결된 문장이며, 인물·기관·발언을 구체적으로 인용해도 됨}

📊 숫자로 보는 현황: {핵심 수치를 담은 1~2문장}
- {구체적 수치·비율·날짜가 들어간 완결 문장 2~4개}

🛢️ 배경 설명: {맥락 1~2문장}
- {배경을 설명하는 완결 문장 2~4개}

📈 반대편 시각: {반대·소수 의견 1~2문장}
- {반대 근거 완결 문장 1~3개. 기사에 없으면 "- 기사 내 반대 의견 없음"}

🎯 관심 포인트: {이 기사가 가리키는 섹터·종목과 지켜볼 이유 1~2문장}
- 관련 섹터: {기사와 직접 관련된 섹터 (예: 반도체, 은행, 에너지). 불명확하면 "특정 섹터 불명확"}
- 관련 종목: {기사에 언급되거나 명백히 영향받는 티커·기업명 1~5개. 없으면 "기사 내 특정 종목 없음"}
- 체크 포인트: {투자자가 지켜볼 지표·이벤트 1~2가지}

🧭 주목할 점: {앞으로의 변수·관전 포인트 1~2문장}
- {앞으로 지켜볼 지점 완결 문장 2~4개}

출처: {매체명}

규칙:
- 각 섹션은 '요지 한 줄' + 그 아래 '완결된 문장 불릿 여러 개'로 구성. 불릿은 정보가 담긴 온전한 문장으로.
- 기사에 나온 인물·기관·발언·수치를 적극 인용해 상세하게. 단, 기사에 없는 사실·수치는 절대 지어내지 말 것 (환각 금지).
- 🎯 관심 포인트는 기사에 등장하거나 명백히 관련된 섹터·종목만 넣을 것. 기사에 근거가 없는 종목은 절대 넣지 말 것.
- 매수·매도·목표주가 등 매매 방향이나 투자 권유를 단정하지 말 것. '지켜볼 포인트' 관점으로만 서술.
- 헤드라인 이모지는 주제에 맞게 (통화정책 ⚖️/🏦, 실적 📊, 유가 🛢️, 반도체 💾 등).
- 마크다운 기호(#, *, **)는 쓰지 말 것. 섹션 이모지와 '- ' 불릿만 사용.
- 기사 정보가 부족한 섹션은 무리해서 채우지 말고 있는 만큼만 쓸 것.
"""


def summarize(article, timeout=120):
    user = (
        f"[출처] {article['source']}\n"
        f"[제목] {article['title']}\n"
        f"[본문]\n{article['body']}\n"
    )
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2000,
        "temperature": 0.3,
        "system": SYSTEM,
        "messages": [
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }r = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=timeout)
    if r.status_code >= 400:
        # 400 등 오류 시 응답 본문을 그대로 노출해 원인(모델명/필드) 파악
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    # content는 블록 리스트 → text 블록만 이어붙임
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(parts).strip()
