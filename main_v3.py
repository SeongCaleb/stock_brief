"""Stock Brief v3 daily email entry point.

Runs beside the original main.py without changing the existing send pipeline.
Safe preview: python main_v3.py --preview
Actual send: python main_v3.py --send
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from config import ANTHROPIC_API_KEY, MAIL_TO, NAVER_PASS, NAVER_USER, _gnews
from mailer import KST, block_html, build_email, glance_html, send
from sources import collect, enrich, load_seen, save_seen
from summarize import headline_of, summarize, triage
from v3_research import dated_articles, research_html, research_snapshot
from v3_market_data import collect_snapshot
from v4_discovery import (discovery_universe, unique_events, load_tracking,
                          tracking_changes, next_tracking, diversify_candidates, TRACKING_PATH)
from v4_email import make_digest
from v4_community import (load_seen as load_community_seen, collect_public_signals,
                          STATE_FILE as COMMUNITY_STATE_FILE)

STATE_PATH = Path("v3_delivery_state.json")
REPORT_DIR = Path("reports")
ADDITIONAL_FEEDS = [
    {"name": "Global Rates and Gold", "market": "US",
     "url": _gnews("treasury yields OR gold OR credit spreads OR central bank when:2d")},
    {"name": "Global Industry Outlook", "market": "US",
     "url": _gnews("utilities OR healthcare OR industrials OR technology OR earnings when:2d")},
    {"name": "International Markets", "market": "US",
     "url": _gnews("Japan OR Europe OR India OR emerging markets stocks when:2d")},
    {"name": "한국 금리·채권·환율", "market": "KR",
     "url": _gnews("한국 국채 금리 금 환율 코스피", lang="ko")},
]


def _load_state():
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(state, dict) and isinstance(state.get("sent_dates"), list):
            return state
    except (OSError, ValueError):
        pass
    return {"sent_dates": []}


def _save_state(state):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _prepare_sources():
    import sources
    sources.FEEDS = list(sources.FEEDS) + ADDITIONAL_FEEDS
    sources.MAX_CANDIDATES = max(sources.MAX_CANDIDATES, 50)


def _update_prompts():
    # Additional instructions are applied to the already working Anthropic pipeline.
    import summarize as model
    model.TRIAGE_SYSTEM += (
        "\n3~6개월 이상 투자 관점에서 주식 지수, 개별기업, 채권, 금, 환율 모두 고려. "
        "섹터 제한 없음. 중요한 시장 구조 변화와 위험 공시를 우선. "
        "단순 가격 급등·급락만으로 곧 버블 붕괴나 긴급 매도를 주장하지 마라. "
        "매수와 매도 명령이 아닌 기사 방향만 제공."
    )
    model.BRIEF_SYSTEM += (
        "\n3~6개월 이상 투자 시야로 요약한다. 기사 주장과 검증된 사실을 구분하고, "
        "원문이 불확실하면 '보도에 따르면'으로 표현한다. "
        "최종 포인트는 확인해야 할 실적·가격·금리·공시 조건에 집중한다. "
        "고평가나 버블 붕괴 여부는 기사 하나만으로 판정하지 않는다."
    )


def asset_comparison_html(snapshot):
    from html import escape
    rows = []
    for a in snapshot.get("asset_classes", []):
        change = a.get("return_3m_pct")
        trend = a.get("ma200_gap_pct")
        rows.append(f"<tr><td>{escape(str(a.get('name', '')))} ({escape(str(a.get('ticker', '')) )})</td>"
                    f"<td>{escape(str(change)) if change is not None else '자료 부족'}%</td>"
                    f"<td>{escape(str(trend)) if trend is not None else '자료 부족'}%</td>"
                    f"<td>{escape(str(a.get('as_of', '')[:10]))}</td></tr>")
    if not rows:
        return "<p>자산별 비교: 검증 가능한 최근 데이터 없음</p>"
    return ("<h3>📊 주식·채권·금 3개월 비교 (매수 추천 아님)</h3>"
            "<table cellpadding='6' style='font-size:12px'><tr><th>자산</th><th>3개월 %</th><th>200일선 대비 %</th><th>기준일</th></tr>"
            + "".join(rows) + "</table><p style='font-size:11px'>USD 기준 가격 변화. ETF별 위험·변동성·환율은 별도 고려.</p>")


def make_email():
    """Collect articles and broad rotating universe, create a concise v4 digest."""
    _prepare_sources()
    _update_prompts()
    seen = load_seen()
    old = load_tracking()
    fetched = collect(seen)
    articles = unique_events(dated_articles(fetched))
    community_old = load_community_seen()
    try:
        community = collect_public_signals(previous=community_old)
    except Exception as exc:
        community = {"items": [], "statuses": {"소스 수집": "실패: " + type(exc).__name__},
                     "next_seen": community_old}
    print("[info] 공개 커뮤니티/영상 새 제목:", len(community["items"]), community["statuses"])
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "community_sources.json").write_text(
        json.dumps({"items": community["items"], "statuses": community["statuses"]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[info] 신규 RSS {len(fetched)}건, 유효 기사 {len(articles)}건")
    selected = unique_events(triage(articles) if articles else [])
    selected = enrich(selected)
    picks, sent_uids = [], []
    for article in selected:
        try:
            brief = summarize(article)
        except Exception as exc:
            print(f"[warn] 기사 요약 오류: {type(exc).__name__}")
            continue
        if len([line for line in brief.splitlines() if line.strip()]) != 3:
            print("[warn] 3줄 형식이 아닌 기사 제외")
            continue
        article["ko_title"] = headline_of(brief) or article["title"]
        article["brief"] = brief
        picks.append(article)
        sent_uids.append(article["uid"])

    REPORT_DIR.mkdir(exist_ok=True)
    snapshot_path = REPORT_DIR / "market_snapshot.json"
    watched = list((old.get("latest") or {}).keys())
    universe = discovery_universe(
        [{"title": x["title"], "summary": ""} for x in community["items"][:3]] + articles,
        previous=watched, extra=os.getenv("STOCK_WATCHLIST"),
        limit=int(os.getenv("DISCOVERY_LIMIT", "18"))
    )
    print(f"[info] 섹터 순환·뉴스 기반 신규 조사 종목 {len(universe)}개")
    try:
        snapshot = collect_snapshot(watchlist=universe)
        print(f"[info] 시장 데이터: 거시 {len(snapshot['macro'])}개, ETF {len(snapshot['asset_classes'])}개, 후보 {len(snapshot['assets'])}개")
    except Exception as exc:
        print(f"[warn] 시장 데이터 수집 실패: {type(exc).__name__}")
        snapshot = {
            "macro": {}, "assets": {}, "asset_classes": [], "watchlist": [],
            "collection_warnings": [f"시장 데이터 수집 실패: {type(exc).__name__}"],
        }
    # Always replace, even on provider failure; never use stale prior snapshot.
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    regime, candidates = research_snapshot(str(snapshot_path))
    candidates = diversify_candidates(candidates, count=3)
    changes = tracking_changes(snapshot, old)
    date_str, html = make_digest(picks, snapshot, regime, candidates, changes, community=community)
    ledger = next_tracking(snapshot, old)
    return date_str, html, seen, sent_uids, len(picks), len(candidates), ledger, community["next_seen"]


def main():
    cli = argparse.ArgumentParser()
    action = cli.add_mutually_exclusive_group(required=True)
    action.add_argument("--preview", action="store_true")
    action.add_argument("--send", action="store_true")
    args = cli.parse_args()
    today = datetime.now(KST).date().isoformat()
    state = _load_state()
    if args.send and today in state["sent_dates"]:
        print(f"[info] {today} 발송 기록이 있어 중복 발송하지 않습니다")
        return

    if args.send:
        missing = [
            key for key, value in {
                "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
                "NAVER_USER": NAVER_USER,
                "NAVER_PASS": NAVER_PASS,
                "MAIL_TO": MAIL_TO,
            }.items() if not value
        ]
        if missing:
            raise RuntimeError("필수 Secret이 설정되지 않았습니다: " + ", ".join(missing))

    date_str, html, seen, sent_uids, news_count, picks_count, ledger, community_state = make_email()
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "latest.html").write_text(html, encoding="utf-8")
    print(f"[info] 보고서 생성: 뉴스 {news_count}건, 조건부 추천 후보 {picks_count}건")
    if args.preview:
        print("[info] 미리보기만 생성했습니다. 메일은 보내지 않았습니다.")
        return

    # SMTP succeeds BEFORE either dedup cache is persisted.
    send(f"📊 Stock Brief v4 · {date_str} | 추천 {picks_count} · 핵심 뉴스 {news_count}", html)
    print(f"[info] 이메일 발송 성공 → {MAIL_TO}")
    seen.update(sent_uids)
    save_seen(seen)
    track_path = Path(TRACKING_PATH)
    track_temp = track_path.with_suffix(".tmp")
    track_temp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    track_temp.replace(track_path)
    community_path = Path(COMMUNITY_STATE_FILE)
    community_tmp = community_path.with_suffix(".tmp")
    community_tmp.write_text(json.dumps(community_state, ensure_ascii=False, indent=2), encoding="utf-8")
    community_tmp.replace(community_path)
    state["sent_dates"] = list(dict.fromkeys([*state["sent_dates"], today]))[-45:]
    _save_state(state)


if __name__ == "__main__":
    main()
