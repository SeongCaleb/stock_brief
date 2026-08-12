"""전역 설정. 모든 env는 '빈 문자열이 들어와도' 하드 폴백으로 죽지 않게 처리."""
import os
import urllib.parse


def _gnews(query, lang="en"):
    """구글 뉴스 RSS 검색 URL 생성 (다매체 헤드라인 집계)."""
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# --- RSS 소스 정의 (미국 + 한국) ------------------------------------------
# market: "US" | "KR"
# 직접 피드: 본문 추출이 잘 돼 요약이 풍부함.
# 구글뉴스 애그리게이터: 매체 폭이 넓고 출처명이 그대로 표시됨(리다이렉트라 본문 추출 실패 시 스니펫 폴백).
FEEDS = [
    # 미국 — 직접 피드
    {"name": "MarketWatch", "market": "US", "url": "http://feeds.marketwatch.com/marketwatch/topstories/"},
    {"name": "CNBC Markets", "market": "US", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"},
    {"name": "Investing.com", "market": "US", "url": "https://www.investing.com/rss/news_25.rss"},
    {"name": "Yahoo Finance", "market": "US", "url": "https://finance.yahoo.com/news/rssindex"},
    # 미국 — 구글뉴스 애그리게이터
    {"name": "구글뉴스", "market": "US", "url": _gnews("US stock market")},
    {"name": "구글뉴스", "market": "US", "url": _gnews("Wall Street stocks earnings")},
    # 한국 — 직접 피드
    {"name": "한국경제", "market": "KR", "url": "https://www.hankyung.com/feed/finance"},
    {"name": "매일경제 증권", "market": "KR", "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "연합뉴스 경제", "market": "KR", "url": "https://www.yna.co.kr/rss/economy.xml"},
    # 한국 — 구글뉴스 애그리게이터
    {"name": "구글뉴스", "market": "KR", "url": _gnews("코스피 증시", lang="ko")},
]

# 메일에 담을 최대 기사 수 (선별 후 최종)
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "").strip() or "5")

# 선별(triage)에 넣을 후보 기사 최대 수 (많이 모아서 이 중 중요한 것만 고름)
MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "").strip() or "25")

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
