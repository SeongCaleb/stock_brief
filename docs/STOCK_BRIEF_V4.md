# Stock Brief V4 — 자동 발굴 + 이메일

## 제공 기능
- RSS 뉴스 + 주요 11개 업종의 대표 미국 종목을 매일 순환 조사합니다. 뉴스에 언급된 종목도 추가합니다.
- 하루 18개 기업을 조사합니다. 글로벌 전종목 스크리닝은 아닙니다.
- yfinance 가격·컨센서스, FRED 지표와 선택적 SEC 공시를 사용하며 자료 지연 가능성을 표시합니다.
- 선행 PER 또는 이익 추정치가 있으면 조사 후보, 근거가 충분하면 조건부 매수 검토로 구분합니다.
- 이메일은 시장 위험 → 후보 최대 3개 → 뉴스 최대 5개 → 주식·채권·금 → 이전 후보 변화 순입니다.
- 발송 성공 후 v4_thesis_history.json에 관찰 기록을 저장합니다.

## 실행
- 기본 예약은 08:30 KST이며 GitHub 예약 실행은 지연될 수 있습니다.
- Actions → Stock Brief v3 Daily Email → Run workflow → send_email=false: 미리보기
- send_email=true: 실제 메일. 같은 KST 날짜 발송 이력이 있으면 중복 발송 방지
- 기존 ANTHROPIC_API_KEY, NAVER_USER, NAVER_PASS, MAIL_TO Secrets 사용
- STOCK_WATCHLIST Variable로 관심 종목 추가 가능. SEC_USER_AGENT는 선택적 보강 자료입니다.

## 한계
- ETF의 3개월 가격수익률은 저평가나 3~6개월 기대수익률을 의미하지 않습니다.
- 대상은 우선 미국 대표주 위주이며 한국·글로벌 상장 종목의 전체 탐색이 아닙니다.
- 기업의 현금흐름 및 실제 투자 가설 성과 검증은 아직 추가 개발이 필요합니다.
- 커뮤니티·유튜브 로그인 전용 콘텐츠는 자동 수집하지 않습니다.
- 인버스/옵션은 자동 주문 대상이 아닙니다. 위험한 헤지는 별도 비용·기간 검토가 필요합니다.

## 검증
- 테스트 후 발송 단계에서 생성된 reports/latest.html, reports/market_snapshot.json은 Actions Artifacts로 확인할 수 있습니다.
- SMTP 성공 로그가 곧 실제 수신함 도착을 보장하지는 않습니다.