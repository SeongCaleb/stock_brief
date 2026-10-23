# Stock Brief v3 — 기존 저장소 통합 안내

이 PR은 기존 `main.py`, `sources.py`, `mailer.py`, `config.py`, `summarize.py`를 **삭제하거나 수정하지 않습니다**.

## 변경사항

- `main_v3.py`: 기존 뉴스 1차 선별 및 3줄 요약 코드를 재사용하고, 중기 투자 관점 및 이메일 확장 섹션을 추가
- `v3_research.py`: 개인 재무 상담 제거, 신선도 검사, 자료가 있을 때만 조건부 추천
- `market_snapshot.json`: 검증된 시장/기업 데이터 입력 형식의 빈 파일 (실시간 시세를 발명하지 않음)
- `.github/workflows/daily.yml`: 매일 오전 8시 30분(KST) v3 발송, 수동 실행은 기본적으로 **미리보기만** 생성
- `tests/test_v3_research.py`: 데이터 부족 시 추천 보류 등 핵심 규칙 시험

## Secrets

기존 **`ANTHROPIC_API_KEY`, `NAVER_USER`, `NAVER_PASS`, `MAIL_TO`** 사용. 이메일 인증정보를 리포지토리에 커밋하지 마세요.
기존 SMTP 포트 465를 `mailer.py` 그대로 재사용합니다.

## 배포 및 테스트

1. 이 PR의 CI 통과를 확인한 뒤 `main`에 병합합니다.
2. Actions → **Stock Brief v3 Daily Email** → Run workflow → `send_email=false` 로 미리보기 생성.
3. Artifacts의 HTML 보고서를 확인합니다.
4. 정상 확인 후 `send_email=true`를 수동 실행해 실제 이메일을 테스트합니다.
5. 다음날 예정된 발송 이력을 확인합니다. 예약 실행은 GitHub에 의해 지연될 수 있습니다.

## 현재 기능 경계

주식·채권·금·ETF에 대한 **투자 추천은 실시간/검증된 자료 연동 전까지 보류됩니다**. `market_snapshot.json`에 신선한 공식 자료/가격/서로 독립된 근거와 반대 논거가 들어올 때만 조건부 추천을 표시합니다. 이 PR은 자동 주식 주문 기능이 없으며, 아카라이브/위폴의 인증이 필요한 콘텐츠는 가져오지 않습니다.

정기 이메일은 최신 뉴스 및 관찰 포인트를 제공하고 시장 데이터가 없을 경우 '판단 보류'를 명시합니다. 이번 PR은 데이터 공급업체 연동이나 포트폴리오 구성 최적화 완료를 의미하지 않습니다.
