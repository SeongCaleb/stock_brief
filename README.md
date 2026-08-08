# 📈 stock_brief — 증시 브리핑 자동 발송

**미국 증시** 뉴스를 RSS로 모아 **Axios "Smart Brevity" 스타일**의 한국어 다이제스트로 요약하고,
기사가 가리키는 **관심 섹터·종목**까지 뽑아 매일 아침 이메일로 보내는 GitHub Actions 파이프라인.

> RSS 수집 → Anthropic(Claude) 요약 → Naver SMTP 발송 → `seen.json` 커밋 백 (중복 방지)

---

## 구조 / Structure

```
stock_brief/
├─ config.py        # RSS 소스 목록, NIM/SMTP 설정 (모든 env 빈값 폴백 처리)
├─ sources.py       # RSS 수집 · 중복 제거 · 본문 추출(trafilatura)
├─ summarize.py     # Anthropic Messages API 호출 + Axios 프롬프트 (관심 섹터·종목 포함)
├─ mailer.py        # Naver SMTP 발송 + 다이제스트 HTML 조립
├─ main.py          # 오케스트레이션 진입점
├─ seen.json        # 열람 기록 캐시 (Actions가 자동 커밋)
├─ requirements.txt
└─ .github/workflows/daily.yml   # 매일 07:00 KST 실행
```

## 설정 / Setup

### 1. GitHub Secrets (`Settings → Secrets and variables → Actions → Secrets`)

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com에서 발급한 `sk-ant-...` 키 |
| `NAVER_USER` | 네이버 메일 주소 (예: `id@naver.com`) |
| `NAVER_PASS` | 네이버 **애플리케이션 비밀번호** (로그인 비번 아님) |
| `MAIL_TO` | 받을 주소 (미설정 시 `NAVER_USER`로 발송) |

### 2. GitHub Variables (선택, `... → Variables`)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | 미설정/빈값이어도 안전하게 기본값 사용. 비용↓ 원하면 `claude-haiku-4-5` |
| `MAX_ARTICLES` | `5` | 메일에 담을 최대 기사 수 |

### 3. 네이버 앱 비밀번호 발급
네이버 → 내정보 → 보안설정 → 애플리케이션 비밀번호 관리에서 발급.
그리고 **메일 환경설정 → POP3/SMTP 사용 설정을 ON** 해야 SMTP 발송이 됩니다.

### 4. 실행
- 자동: 매일 07:00 KST (`cron: "0 22 * * *"` — UTC 기준)
- 수동: Actions 탭 → **Stock Brief Daily** → **Run workflow**

## 소스 커스터마이징
`config.py`의 `FEEDS` 리스트만 수정하면 됩니다. (API 키 불필요)
- 직접 피드: `{"name": "표시명", "url": "RSS 주소"}` — 본문 추출이 잘 돼 요약이 풍부함.
- 구글뉴스 애그리게이터: `{"name": "구글뉴스", "url": _gnews("검색어")}` — Bloomberg·Reuters·WSJ 등 다매체 헤드라인을 한 번에 수집하고, 각 기사의 실제 출처명이 표시됨.
  - 검색어만 바꾸면 관심 주제로 좁힐 수 있음 (예: `_gnews("semiconductor stocks")`).
  - 단, 리다이렉트 링크라 본문 추출 실패 시 스니펫 기반이라 요약이 짧아질 수 있음.

> Bloomberg·JP모건 등은 무료 뉴스 RSS를 제공하지 않으므로 직접 피드로는 붙일 수 없고, 위 구글뉴스 애그리게이터를 통해 해당 매체 헤드라인이 들어옵니다.

## 설계 노트 / Design notes
- **빈 env 방지**: 모든 `os.getenv(...)`에 `.strip() or 기본값` 폴백 — 빈 문자열이 들어와도 죽지 않음.
- **seen.json 영속성**: 워크플로가 실행 후 변경분을 리포에 커밋(`permissions: contents: write`). 무한 성장 방지 위해 최근 2000건만 유지.
- **실패 격리**: 요약에 성공한 기사만 `seen`에 기록 → 실패 건은 다음 실행 때 재시도. 메일 발송 성공 후에만 캐시 저장.
- **본문 폴백**: 본문 추출이 짧으면(`< MIN_BODY_CHARS`) RSS 요약으로 대체.
- **관심 섹터·종목**: 각 기사 요약 끝에 `🎯 관심 포인트`(관련 섹터/종목/체크포인트)를 붙임. 기사에 근거가 있는 종목만 추출하며, 매수·매도 방향은 단정하지 않음.
- **면책**: 메일 하단에 "매수·매도 추천이나 투자 자문이 아니다"라고 명시. 이 파이프라인은 뉴스 기반 참고 정보 제공용이며 투자 자문이 아닙니다.
- **실행 내 중복 제거**: uid + 정규화 제목 기준으로, 여러 피드(직접+구글뉴스)가 같은 기사를 실어도 한 번만 선정.

## ⚠️ 검증 안내
샌드박스 네트워크 제약으로 **RSS 엔드포인트/NIM/SMTP 실제 연결은 로컬 테스트하지 못했습니다.**
파싱·중복제거·HTML 생성·env 가드는 검증 완료. 첫 실행은 Actions에서 **Run workflow**로 수동 트리거해
로그를 확인하세요. 일부 RSS 주소는 매체 사정으로 바뀔 수 있으니 실패 로그가 뜨면 `config.py`에서 교체하면 됩니다.
