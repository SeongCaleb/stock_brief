"""전역 설정. 모든 env는 '빈 문자열이 들어와도' 하드 폴백으로 죽지 않게 처리."""
import os
import urllib.parse


def _gnews(query):
    """구글 뉴스 RSS 검색 URL 생성 (Bloomberg·Reuters·WSJ 등 다매체 헤드라인 집계)."""
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# --- RSS 소스 정의 (미국 증시 전용) ---------------------------------------
# 직접 피드: 본문 추출이 잘 돼 요약이 풍부함.
# 구글뉴스 애그리게이터: 매체 폭이 넓고(블룸버그·로이터 포함) 출처명이 그대로 표시됨.
#   단, 리다이렉트 링크라 본문 추출 실패 시 스니펫 기반으로 요약이 짧아질 수 있음.
FEEDS = [
    # 직접 피드 (본문 풍부)
    {"name": "MarketWatch", "url": "http://feeds.marketwatch.com/marketwatch/topstories/"},
    {"name": "CNBC Markets", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"},
    {"name": "Investing.com", "url": "https://www.investing.com/rss/news_25.rss"},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    # 구글뉴스 애그리게이터 (다매체 헤드라인 — 실제 출처명 표시)
    {"name": "구글뉴스", "url": _gnews("US stock market")},
    {"name": "구글뉴스", "url": _gnews("Wall Street stocks earnings")},
]

# 메일에 담을 최대 기사 수
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "").strip() or "8")

# 추출 본문이 이 길이 미만이면 RSS 요약으로 폴백
MIN_BODY_CHARS = 400

# --- LLM (Anthropic Messages API) -----------------------------------------
ANTHROPIC_API_URL = os.getenv("ANTHROPIC_API_URL", "").strip() or "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "").strip() or "2023-06-01"
# ★ 빈 env가 들어와도 죽지 않도록 하드 폴백 (예전 ANTHROPIC_MODEL 빈값 이슈 방지)
#   비용을 줄이려면 "claude-haiku-4-5"로 교체 가능
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# --- 메일 (Naver SMTP) ----------------------------------------------------
NAVER_USER = os.getenv("NAVER_USER", "").strip()
NAVER_PASS = os.getenv("NAVER_PASS", "").strip()          # 네이버 '애플리케이션 비밀번호'
MAIL_TO = os.getenv("MAIL_TO", "").strip() or NAVER_USER  # 미지정 시 본인에게
SMTP_HOST = "smtp.naver.com"
SMTP_PORT = 465

# 열람 기록 캐시 경로
SEEN_PATH = os.getenv("SEEN_PATH", "").strip() or "seen.json"
