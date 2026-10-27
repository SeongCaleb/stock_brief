"""Stock Brief V5 decision layer.

Dated, conservative heuristics for a discretionary investor with a 3–6+ month
horizon. This is a *model portfolio example*, not a personalized allocation,
fair-value appraisal, return forecast or automated trading instruction.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from math import isfinite

WEIGHTS = {
    "growth": 25, "valuation": 20, "financial_health": 20,
    "catalyst": 15, "trend": 10, "reward_risk": 10,
}
ASSET_WEIGHTS = {
    "neutral": {"cash_short": 45, "us_index": 25, "international": 15, "single_stocks": 10, "gold": 5},
    "risk_on": {"cash_short": 25, "us_index": 35, "international": 15, "single_stocks": 20, "gold": 5},
    "risk_off": {"cash_short": 55, "us_index": 20, "international": 15, "single_stocks": 5, "gold": 5},
    "stress": {"cash_short": 65, "us_index": 15, "international": 10, "single_stocks": 5, "gold": 5},
}
ASSET_NAMES = {
    "cash_short": "현금·초단기채(SGOV 등)",
    "us_index": "미국 주식지수(VOO 등)",
    "international": "미국 외 주식(VXUS 등)",
    "single_stocks": "개별 주식",
    "gold": "금(IAU 등)",
}


def num(value):
    try:
        v = float(value)
        return v if isfinite(v) else None
    except (ValueError, TypeError):
        return None


def fresh(datum, now=None, days=9):
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(str(datum["as_of"]).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return False
        age = (now - dt).total_seconds() / 86400
        return -1 <= age <= days
    except (KeyError, ValueError, TypeError):
        return False


def _metric(macro, key, now):
    data = macro.get(key) or {}
    return num(data.get("value")) if fresh(data, now=now) else None


def classify_market(snapshot, now=None):
    """Require multiple independent observed indicators; SPY trend != breadth."""
    now = now or datetime.now(timezone.utc)
    macro = snapshot.get("macro") or {}
    vix = _metric(macro, "vix", now)
    spread = _metric(macro, "high_yield_spread_pct", now)
    rate10 = _metric(macro, "us_10y_yield_pct", now)
    trend = _metric(macro, "spy_200dma_gap_pct", now)
    observed = sum(x is not None for x in (vix, spread, rate10, trend))
    context = []
    if vix is not None:
        context.append(f"VIX {vix:.1f}")
    if spread is not None:
        context.append(f"하이일드 스프레드 {spread:.2f}%p")
    if rate10 is not None:
        context.append(f"10년 국채 {rate10:.2f}%")
    if trend is not None:
        context.append(f"SPY 200일선 대비 {trend:+.1f}%")
    # Equal-weight vs capitalization-weight S&P 500 is a concentration proxy,
    # not a direct measure of advance/decline market breadth.
    comparison = {x.get("ticker"): x for x in (snapshot.get("asset_classes") or [])}
    voo, rsp = comparison.get("VOO", {}), comparison.get("RSP", {})
    narrow = False
    if fresh(voo, now=now) and fresh(rsp, now=now):
        voo_r3, rsp_r3 = num(voo.get("return_3m_pct")), num(rsp.get("return_3m_pct"))
        if voo_r3 is not None and rsp_r3 is not None:
            gap = rsp_r3 - voo_r3
            context.append(f"동일가중-시총가중 3개월 격차 {gap:+.1f}%p(집중도 대용)")
            narrow = gap <= -3
    rate_pressure = rate10 is not None and rate10 >= 4.7
    if observed < 3 or vix is None or spread is None:
        return {
            "code": "unknown", "label": "시장 판단 유보", "observed": observed,
            "reasons": context, "missing": "VIX·신용 스프레드 및 기타 지표 1개 이상 필요",
            "note": "시장의 상승 종목 비율 및 광범위한 EPS 전망 데이터가 없어 완전한 시장 국면 진단이 아닙니다.",
        }
    severe = (vix >= 32 and spread >= 5) or (spread >= 5.5 and trend is not None and trend <= -10)
    warnings = sum((vix >= 27, spread >= 4.2, trend is not None and trend <= -7))
    if severe:
        code, label = "stress", "시장 스트레스 · 방어 우선"
    elif warnings >= 2:
        code, label = "risk_off", "위험 회피 · 신규 진입 축소"
    elif vix <= 20 and spread <= 3.5 and trend is not None and trend >= 2 and not narrow and not rate_pressure:
        code, label = "risk_on", "위험 선호 · 선별 진입 확대 검토"
    else:
        code, label = "neutral", "중립 · 분할 진입"
    if narrow or rate_pressure:
        context.append("상승 집중 또는 높은 자금조달 금리 부담 존재")
    return {
        "code": code, "label": label, "observed": observed,
        "reasons": context, "missing": "시장 참여 폭·기업 이익 전망의 직접 측정 없음",
        "note": "거시 지표의 실용적 휴리스틱이며 버블 붕괴 확률이나 주가 전환 시점은 예측하지 않습니다.",
    }


def allocation(market, last=None):
    """Illustrative allocation, damped to at most 5 percentage points/day/class."""
    if market["code"] == "unknown":
        return {"weights": (last or ASSET_WEIGHTS["neutral"]).copy(),
                "status": "판단 유보 · 중립 예시 유지", "changed": False, "investable": False}
    target = ASSET_WEIGHTS[market["code"]]
    if not isinstance(last, dict) or set(last) != set(target) or sum(last.values()) != 100:
        return {"weights": target.copy(), "status": "시장 국면별 예시 배분", "changed": True, "investable": False}
    # Keep sum=100: capped transfers from overweight to underweight buckets.
    result = {k: int(last[k]) for k in target}
    decreases = [k for k in result if result[k] > target[k]]
    increases = [k for k in result if result[k] < target[k]]
    for from_key in decreases:
        transferable = min(5, result[from_key] - target[from_key])
        for to_key in increases:
            amount = min(transferable, 5 - (result[to_key]-last[to_key]),
                         target[to_key] - result[to_key])
            if amount <= 0:
                continue
            result[from_key] -= amount
            result[to_key] += amount
            transferable -= amount
            if transferable == 0:
                break
    assert sum(result.values()) == 100
    return {"weights": result, "status": "이전 모델 대비 하루 항목별 최대 5%p 조정",
            "changed": result != last, "investable": False}


def scenarios(candidate):
    """Illustrative valuation *sensitivity*, not calibrated price targets.

    Uses current price anchored to current vendor forward EPS estimate:
    P_future = P_now × (1 + EPS_revision) × (1 + PE_repricing)
    Neither revision nor repricing is a probability forecast.
    """
    market = candidate.get("market_info") or {}
    valuation = candidate.get("valuation_info") or {}
    price = num(market.get("price"))
    pe = num(valuation.get("forward_pe"))
    if price is None or price <= 0 or pe is None or pe <= 0:
        return None
    cases = {
        "bear": {"eps_revision_pct": -15, "pe_change_pct": -15},
        "base": {"eps_revision_pct": 0, "pe_change_pct": 0},
        "bull": {"eps_revision_pct": 10, "pe_change_pct": 10},
    }
    for case in cases.values():
        case["price"] = round(price * (1 + case["eps_revision_pct"]/100) * (1 + case["pe_change_pct"]/100), 2)
        case["return_pct"] = round(100*(case["price"]/price - 1), 1)
    # This is NOT an entry order or intrinsic valuation. It is a conditional
    # comparison zone inferred from peer multiples, when reliable values exist.
    peer = num(valuation.get("peer_forward_pe_median"))
    entry = None
    if peer is not None and peer > 0 and 0.5 <= peer/pe <= 1.5:
        anchor = price * min(1.0, peer/pe)
        entry = [round(anchor*0.95, 2), round(anchor, 2)]
    return {"anchor_price": round(price, 2), "cases": cases, "peer_entry_zone": entry,
            "model": "선행 EPS 추정치 변동 × 선행 P/E 재평가 민감도(확률/목표가 아님)"}


def _score_factor(v, low, high, weight, invert=False):
    if v is None:
        return 0, False
    pct = max(0.0, min(1.0, (v-low)/(high-low)))
    return round(weight * (1-pct if invert else pct)), True


def evaluate_candidate(candidate, market):
    """Score using measured inputs; separate evidence coverage and judgment."""
    c = dict(candidate)
    m = c.get("market_info") or {}
    v = c.get("valuation_info") or {}
    d = c.get("detail") or {}
    growth = num(v.get("expected_earnings_growth_pct"))
    rev = num(d.get("revenue_growth_yoy_pct"))
    pe = num(v.get("forward_pe"))
    peer = num(v.get("peer_forward_pe_median"))
    fcf = num(d.get("fcf_yield_pct"))
    margin = num(d.get("operating_margin_pct"))
    debt = num(d.get("net_debt_bil_usd"))
    r3 = num(m.get("return_3m_pct"))
    high = num(m.get("below_52w_high_pct"))
    buckets = {}
    buckets["growth"], growth_ok = _score_factor(growth if growth is not None else rev, -10, 35, 25)
    if pe is not None and pe > 0:
        ratio = pe / peer if peer and peer > 0 else None
        val = ratio if ratio is not None else pe / 22
        buckets["valuation"], val_ok = _score_factor(val, .7, 2.0, 20, invert=True)
    else:
        buckets["valuation"], val_ok = 0, False
    fcf_points, fcf_ok = _score_factor(fcf, -3, 7, 12)
    margin_points, margin_ok = _score_factor(margin, -5, 30, 8)
    buckets["financial_health"] = fcf_points + margin_points
    catalyst_ok = growth is not None or rev is not None
    buckets["catalyst"] = min(15, round(max(0, buckets["growth"])*.5)) if catalyst_ok else 0
    trend_points, trend_ok = _score_factor(r3, -20, 18, 10)
    if high is not None and high > -1 and r3 is not None and r3 > 25:
        trend_points = min(trend_points, 3)
    buckets["trend"] = trend_points
    risk_count = len(c.get("risk_tags") or [])
    buckets["reward_risk"] = max(0, 8 - 3*risk_count - (4 if market["code"] in ("risk_off", "stress") else 0))
    score = sum(buckets.values())
    # Count independently observed analytical dimensions (not volume of news).
    coverage = sum((growth_ok, val_ok, fcf_ok or margin_ok, catalyst_ok, trend_ok))
    evidence = "높음" if coverage >= 5 else "보통" if coverage >= 3 else "제한적"
    data_reliability = "벤더 참고" if coverage >= 3 else "자료 제한"
    price_attractiveness = ("비교 유보" if peer is None else
                            "유리" if buckets["valuation"] >= 14 else
                            "부담" if buckets["valuation"] <= 6 else "중립")
    reasons = []
    if coverage < 3:
        action = "대기"; reasons.append("핵심 가격·실적·현금흐름 지표 부족")
    elif market["code"] == "stress":
        action = "대기"; reasons.append("시장 복합 스트레스")
    elif growth is not None and growth < -20 and pe is not None and pe > 45:
        action = "제외"; reasons.append("예상 이익 감소와 높은 선행 PER 동시 발생")
    elif risk_count >= 2:
        action = "대기"; reasons.append("고평가·과열 경고 복수")
    elif pe is not None and peer is None and growth is not None and growth >= 50 and pe < 18:
        action = "조건부 진입 대기"; reasons.append("고성장·저PER 조합의 이익 예상기간 및 공급업체 추정 기준 재확인")
    elif r3 is not None and r3 < -15:
        action = "조건부 진입 대기"; reasons.append("3개월 급락에 따른 하락 추세·실적 원인 확인")
    elif market["code"] in ("risk_off", "unknown"):
        action = "조건부 진입 대기"; reasons.append("시장 환경과 근거 확인 후 판단")
    elif score >= 68 and coverage >= 4:
        action = "분할 매수 검토"; reasons.append("상대적으로 양호한 성장·가격·재무 조건")
    elif score >= 45:
        action = "조건부 진입 대기"; reasons.append("가격/가설 확인 조건 필요")
    else:
        action = "대기"; reasons.append("기대 수익 대비 불확실성 또는 가격 부담")
    c.update({"score_v5": score, "score_breakdown": buckets,
              "coverage_v5": coverage, "data_reliability": data_reliability,
              "thesis_confidence": evidence, "price_attractiveness": price_attractiveness,
              "action_v5": action, "decision_reasons": reasons,
              "scenario_v5": scenarios(c)})
    return c


def _benchmark(snapshot, ticker):
    return next((a for a in snapshot.get("asset_classes") or [] if a.get("ticker") == ticker), None)


def build_decisions(snapshot, market, candidates, previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    decisions = [evaluate_candidate(c, market) for c in candidates]
    decisions.sort(key=lambda c: (c["action_v5"] == "분할 매수 검토",
                                  c["action_v5"] == "조건부 진입 대기",
                                  c["score_v5"]), reverse=True)
    chosen, industries = [], set()
    for c in decisions:
        sector = c.get("sector") or "미분류"
        if sector not in industries or sector == "미분류":
            chosen.append(c)
            industries.add(sector)
            if len(chosen) == 3:
                break
    if len(chosen) < 3:
        chosen += [c for c in decisions if c not in chosen][:3-len(chosen)]
    found = {c["ticker"] for c in decisions}
    for item in (snapshot.get("watchlist") or []):
        ticker = item.get("ticker")
        if ticker and ticker not in found:
            decisions.append({
                "ticker": ticker, "name": item.get("name", ticker),
                "action_v5": "대기", "score_v5": None,
                "market_info": item.get("market", {}),
                "decision_reasons": ["가격 또는 최소 실적 지표 수집 실패"],
                "data_reliability": "자료 제한",
                "thesis_confidence": "제한적", "price_attractiveness": "미평가",
            })
    return chosen, decisions


def observed_performance(previous, snapshot):
    """Compare price-only returns from first recorded decision, never actual trades."""
    history = (previous or {}).get("observations") or []
    earliest = {}
    latest = {}
    for item in history:
        ticker = item.get("ticker")
        if ticker:
            earliest.setdefault(ticker, item)
            latest[ticker] = item
    outcomes = []
    voo = _benchmark(snapshot, "VOO") or {}
    current_voo = num(voo.get("price"))
    for ticker, old in earliest.items():
        now_item = (snapshot.get("assets") or {}).get(ticker)
        if now_item:
            current = num((now_item.get("market") or {}).get("price"))
        else:
            current = num(latest.get(ticker, {}).get("price"))
        entry = num(old.get("price"))
        if not current or not entry or entry <= 0:
            continue
        ret = round(100*(current/entry-1), 1)
        index_first = num(old.get("voo_price"))
        benchmark_ret = round(100*(current_voo/index_first-1), 1) if current_voo and index_first and index_first>0 else None
        samples = [num(p.get("price")) for p in history if p.get("ticker") == ticker]
        samples = [v for v in samples if v is not None]
        samples.append(current)
        high_return = round(100*(max(samples)/entry-1),1) if samples else None
        low_return = round(100*(min(samples)/entry-1),1) if samples else None
        outcomes.append({
            "observed_max_pct": high_return, "observed_min_pct": low_return,
            "ticker": ticker, "since": old.get("date"), "original_decision": old.get("action"),
            "last_decision": latest[ticker].get("action"), "price_return_pct": ret,
            "benchmark_price_return_pct": benchmark_ret,
            "excess_pct": round(ret-benchmark_ret,1) if benchmark_ret is not None else None,
            "benchmark": "VOO 가격(배당 제외)",
            "note": "추천/대기 가설의 관찰 수익률; 실제 매매나 총수익률 아님",
        })
    return outcomes


def update_history(previous, decisions, snapshot, market, alloc, now=None):
    """Persist all inspected candidates, including rejected and deferred ideas."""
    previous = previous if isinstance(previous, dict) else {}
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    log = list(previous.get("observations") or [])
    recent = {x.get("ticker"):x for x in log}
    voo = _benchmark(snapshot, "VOO") or {}
    current_voo = num(voo.get("price"))
    changes = []
    for item in decisions:
        ticker = item.get("ticker")
        quote = item.get("market_info") or {}
        price = num(quote.get("price"))
        if not ticker or price is None:
            continue
        action = item.get("action_v5", "대기")
        previous_item = recent.get(ticker)
        if previous_item and previous_item.get("action") != action:
            changes.append(f"{ticker}: {previous_item.get('action')} → {action} (점수·근거 갱신)")
        record = {
            "date": day, "ticker": ticker, "action": action, "price": price,
            "price_as_of": quote.get("as_of") or item.get("quote_date"),
            "voo_price": current_voo,
            "score": item.get("score_v5"), "reason": "; ".join(item.get("decision_reasons") or [])[:160],
        }
        log = [x for x in log if not (x.get("date")==day and x.get("ticker")==ticker)]
        log.append(record)
    log = log[-2500:]
    return {
        "version": 5, "observations": log, "last_updated": day,
        "last_allocation": alloc["weights"], "last_market_regime": market["code"],
    }, changes[:8]
