"""증시 브리핑 파이프라인: 수집 → 선별(중요 뉴스+신호) → 본문보강 → 짧은 요약 → 메일 → 캐시."""
import sys

from config import ANTHROPIC_API_KEY, MAIL_TO, NAVER_PASS, NAVER_USER
from mailer import block_html, build_email, glance_html, send
from sources import collect, enrich, load_seen, save_seen
from summarize import headline_of, summarize, triage


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

    # 2) 후보 수집 (제목+요약, 넉넉히)
    seen = load_seen()
    candidates = collect(seen)
    if not candidates:
        print("[info] 새 기사 없음. 종료.")
        return
    print(f"[info] 후보 {len(candidates)}건 수집")

    # 3) 선별: 꼭 알아야 할 뉴스만 + 방향 신호
    selected = triage(candidates)
    if not selected:
        print("[info] 선별된 중요 뉴스 없음. 종료.")
        return
    print(f"[info] 중요 뉴스 {len(selected)}건 선별")
    for a in selected:
        print(f"   · [{a.get('signal','중립')}] {a['title'][:50]}")

    # 4) 선별된 것만 본문 보강
    selected = enrich(selected)

    # 5) 짧은 브리핑 요약 (성공한 것만 seen 처리)
    blocks = []
    picks = []
    for a in selected:
        try:
            brief = summarize(a)
        except Exception as e:
            print(f"[warn] 요약 실패 [{a['source']}] {a['title']}: {e}")
            continue
        a["ko_title"] = headline_of(brief) or a["title"]  # 상단 목록용 한글 헤드라인
        blocks.append(block_html(a["source"], a.get("market", "US"), a["link"], brief))
        picks.append(a)
        seen.add(a["uid"])
        print(f"[ok] 요약 완료 [{a.get('signal','중립')}] {a['title'][:40]}")

    if not blocks:
        print("[info] 생성된 요약 없음. 메일 미발송.")
        return

    # 6) 메일 발송 (상단 한눈에 보기 + 본문 블록)
    date_str, html = build_email(glance_html(picks), blocks)
    send(f"📈 오늘의 증시 브리핑 · {date_str}", html)
    print(f"[info] 메일 발송 완료 → {MAIL_TO} ({len(blocks)}건)")

    # 7) 발송 성공 후에만 캐시 저장
    save_seen(seen)


if __name__ == "__main__":
    main()
