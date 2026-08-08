"""증시 브리핑 파이프라인 진입점: 수집 → 요약 → 메일 → 캐시 갱신."""
import sys

from config import ANTHROPIC_API_KEY, MAIL_TO, NAVER_PASS, NAVER_USER
from mailer import block_html, build_email, send
from sources import collect, enrich, load_seen, save_seen
from summarize import summarize


def main():
    # 1) 필수 env 확인
    missing = [k for k, v in {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "NAVER_USER": NAVER_USER,
        "NAVER_PASS": NAVER_PASS,
    }.items() if not v]
    if missing:
        print(f"[error] 환경변수 누락: {', '.join(missing)}")
        sys.exit(1)

    # 2) 수집 + 중복 제거
    seen = load_seen()
    articles = collect(seen)
    if not articles:
        print("[info] 새 기사 없음. 종료.")
        return
    print(f"[info] 새 기사 {len(articles)}건 선정")

    # 3) 본문 채우기
    articles = enrich(articles)

    # 4) 요약 (성공한 기사만 seen 처리 → 실패 건은 다음 실행 때 재시도)
    blocks = []
    for a in articles:
        try:
            digest = summarize(a)
        except Exception as e:
            print(f"[warn] 요약 실패 [{a['source']}] {a['title']}: {e}")
            continue
        blocks.append(block_html(a["source"], a["market"], a["link"], digest))
        seen.add(a["uid"])
        print(f"[ok] 요약 완료 [{a['market']}] {a['title'][:40]}")

    if not blocks:
        print("[info] 생성된 요약 없음. 메일 미발송.")
        return

    # 5) 메일 발송
    date_str, html = build_email(blocks)
    send(f"📈 오늘의 증시 브리핑 · {date_str}", html)
    print(f"[info] 메일 발송 완료 → {MAIL_TO} ({len(blocks)}건)")

    # 6) 발송 성공 후에만 캐시 저장
    save_seen(seen)


if __name__ == "__main__":
    main()
