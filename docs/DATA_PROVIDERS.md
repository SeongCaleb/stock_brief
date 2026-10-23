# v3 시장 데이터 자동 수집

매일 v3 뉴스 이메일 생성 시 `v3_market_data.py`가 시장 데이터를 수집하고 `reports/market_snapshot.json`에 보관합니다. GitHub에는 이 산출물을 자동 커밋하지 않습니다.

## 공급원
- **FRED CSV**: VIX(VIXCLS), 미국 하이일드 신용 스프레드(BAMLH0A0HYM2), 2년/10년 미국 국채 금리(DGS2/DGS10). 별도 API 키 없음
- **yfinance / Yahoo Finance**: 미국·해외 ETF(Voo, QQQM, RSP, VXUS, SHY, IEF, TLT, IAU), SPY, 제한된 개별 주식 워치리스트의 일봉·선행 PER·EPS 성장률 추정. 공식 거래소 실시간 시세가 아니며 정확성·가용성 보장 불가
- **SEC**: 기업의 최근 10-K/10-Q 제출 문서 확인. 선택적 환경변수 `SEC_USER_AGENT`에 서비스 이름+연락 가능한 이메일 입력 시 활성화. SEC 공시 링크는 자료 확인용이며 Yahoo의 선행 PER·컨센서스 자체를 SEC가 보증하지 않음

## GitHub Variables
- `SEC_USER_AGENT`: 예: `StockBrief Research contact@example.org` (실제 연락 가능한 주소 사용).
- `STOCK_WATCHLIST`: 콤마로 구분한 티커 목록, 최대 12개. 기본: `BRK-B,JNJ,V,MSFT,GOOGL,XOM`. 업종 제한 없이 변경 가능하나 **전 세계 자동 스크리닝이 아님**.

현재 `.github/workflows/daily.yml`에는 다음 환경 변수 두 개를 전달하도록 추가해야 합니다. `SEC_USER_AGENT`가 없으면 **종목 확정 추천은 보류**합니다.

```yaml
SEC_USER_AGENT: ${{ vars.SEC_USER_AGENT }}
STOCK_WATCHLIST: ${{ vars.STOCK_WATCHLIST }}
```

## 검증 경계
1. 주요 거시 데이터·시장 수치에는 기준일 및 자료원 저장
2. 피드/시세/공시 연동 실패 시 부분 자료만 표시하며 성공한 것처럼 처리하지 않음
3. ETF 비교는 달러 기준 가격 변화이며 원화 수익률·환헤지·배당금·세금·거래 비용 포함 아님
4. 고평가 측정은 단순한 동종기업 비교와 EPS 추정 참고치로 **완전한 기업 가치평가가 아님**
5. VIX·신용스프레드·SPY 200일선은 스트레스 신호일 뿐 시장 폭·닷컴버블 확정 진단 아님
6. 독립된 뉴스/공시 근거와 정성 검증, 가설 성과 추적, 리밸런싱 계획은 추가 개발 필요
7. 실제 투자 주문이나 인버스 자동매매 없음

## 실행 확인
Actions > Stock Brief v3 Daily Email > Run workflow > send_email=false 후 `reports/latest.html` 아티팩트를 검토합니다. 실시간 공급원에서 요청을 거절할 수 있으므로 수집 경고를 우선 확인하세요.
