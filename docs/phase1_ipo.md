# Phase 1 (MVP) — Step 0~6 파이프라인 IPO 명세

> 기획안 2-4의 Phase 1 범위. Step 1~6 핵심 경로(수집 → 중복 제거 → 분류 → 요약 → 대시보드 발행)를
> 로컬 수동 실행으로 완성해 "브리핑 한 통을 실제로 받아보는 것"이 목표.
> Config 스키마·Gemini 연동·알림 규칙 등 이후 Phase가 공유하는 공통 기반도 이 문서에서 정의한다.

## 1. Step별 IPO 상세

### Step 0. 시작 (`step0_init.py`)

- **Input**: 없음 (스케줄러가 매일 08:00 트리거)
- **Process**:
  1. `config/*.yaml`, `sources/feeds.yaml` 로드 및 스키마 검증
  2. 설정 파일 파싱 실패 시 즉시 중단 + 실패 알림 발송
  3. 오늘 날짜 기준 `data/*/YYYY-MM-DD.json` 경로 생성
- **Output**: 검증된 설정 객체 (다음 Step에 전달) 또는 실행 중단
- **실패 처리**: `notify.py`로 관리자 이메일에 "설정 로드 실패" 알림

### Step 1. 수집 (`step1_collect.py`)

- **Input**: `sources/feeds.yaml` (RSS URL 목록), 최근 24시간 기준 시각
- **Process**:
  1. `feedparser`로 각 소스 순회, 최근 24시간 내 기사만 필터링
  2. 접속 실패 소스는 3회 재시도(exponential backoff), 최종 실패 시 로그 기록 후 계속 진행
  3. 메타데이터 정규화: `{title, url, source, published_at, raw_text}`
  4. 네이버 뉴스 검색 API로 국내 키워드 보강 수집
- **Output**: `data/raw/YYYY-MM-DD.json` — 기사 배열
- **실패 처리**: 특정 소스 3회 연속 0건이면 소스 상태 경고 로그 (2-2절 "조용한 품질 열화" 대응)

```json
// data/raw/YYYY-MM-DD.json 스키마
[
  {
    "id": "sha1(url)",
    "title": "string",
    "url": "string",
    "source": "string",
    "published_at": "ISO8601",
    "raw_text": "string"
  }
]
```

### Step 2. 중복 제거 (`step2_dedup.py`)

- **Input**: Step 1 결과, `config/company_aliases.yaml`
- **Process**:
  1. 기업명 정규화 (`company_aliases.yaml` 매핑 적용)
  2. Gemini API에 제목+본문 앞부분을 배치로 전달해 동일 사건 클러스터링
  3. 클러스터별 대표 기사 선정 — `source_tiers.yaml` 1차(원출처) 우선
- **Output**: `data/dedup/YYYY-MM-DD.json` — 중복 제거된 기사 + `cluster_id`
- **Gemini 프롬프트 요지**: "다음 기사 목록 중 같은 사건을 다루는 것끼리 묶어 JSON 배열로 반환" (출력 포맷 강제, 3장 참고)

### Step 3. 분류 (`step3_classify.py`)

- **Input**: Step 2 결과, `config/categories.yaml`, `config/keywords.yaml`
- **Process**:
  1. 화이트리스트/블랙리스트(`keywords.yaml`) 1차 필터링
  2. Gemini API로 "핵심 / 확인 필요 / 제외" 3단 분류 + 카테고리 태깅(메모리/파운드리/장비·소재/팹리스·설계/규제·정책)
  3. 기업 미특정 + 규제 키워드 매칭 시 "규제·정책" 분류
- **Output**: `data/classified/YYYY-MM-DD.json` — `{tier: "핵심"|"확인 필요"|"제외", category: [...]}`

### Step 4. 요약 (`step4_summarize.py`)

- **Input**: Step 3 결과 중 "핵심" 태그 기사, `config/source_tiers.yaml`
- **Process**:
  1. Gemini API로 기사당 3~5문장 요약 생성
  2. 소스 등급 기준 `[확정]`/`[관측]` 태그 부여 (2차 소스는 "발표했다"→확정, "알려졌다"→관측)
  3. 요약 실패(API 에러·형식 오류) 시 헤드라인+링크만 폴백 저장
- **Output**: `data/summarized/YYYY-MM-DD.json`

### Step 5. 조립 (`step5_assemble.py`)

- **Input**: Step 4 결과, 브리핑 템플릿
- **Process**: ①오늘의 핵심 ②카테고리별 ③확인 필요 목록 ④수집 상태(소스별 건수 vs 최근 7일 평균) 순으로 마크다운 아카이브 문서와 HTML 대시보드 페이지를 함께 생성. 대시보드 생성 코드는 기사 데이터·통계만 사용하며 환경변수/Secrets를 참조하지 않고, 외부 소스 텍스트는 모두 이스케이프 처리(XSS 방지)
- **Output**: `data/archive/YYYY-MM-DD.md` (아카이브), `data/dashboard/YYYY-MM-DD.html` (해당 날짜 대시보드), `data/dashboard/index.html` (날짜별 목록 + 최근 실행 상태 배지), `data/dashboard/style.css` (공유 스타일시트)

### Step 6. 저장 확인 (`step6_send.py`)

- **Input**: Step 5 결과 (`data/dashboard/` 산출물)
- **Process**: 대시보드 HTML(`YYYY-MM-DD.html`, `index.html`)이 정상 생성됐는지 확인. GitHub Actions 워크플로우가 이 산출물을 GitHub Pages에 배포
- **Output**: 저장 확인 완료 로그. 브리핑 "본문"은 더 이상 이메일로 발송하지 않고 GitHub Pages 대시보드에서 확인
- **실패 처리**: 08:30까지 대시보드가 갱신되지 않으면 관리자 이메일로 실패 알림 발송("뉴스 없는 날"과 구분되는 별도 알림) — 이 알림 자체는 Gmail SMTP를 계속 사용

---

## 2. Config 파일 스키마

### `config/company_aliases.yaml`
```yaml
samsung_electronics:
  aliases: ["삼성전자", "Samsung Electronics", "005930"]
  segment: ["메모리", "파운드리", "시스템반도체"]
sk_hynix:
  aliases: ["SK하이닉스", "SK Hynix", "000660"]
  segment: ["메모리", "HBM"]
```

### `config/categories.yaml`
```yaml
메모리:
  segment: ["메모리", "HBM"]
파운드리:
  segment: ["파운드리", "시스템반도체"]
장비·소재:
  segment: ["장비", "EUV"]
팹리스·설계:
  segment: ["팹리스", "GPU", "CPU", "AI가속기", "모바일AP", "IP", "설계"]
규제·정책:
  segment: []   # 교차 카테고리, 키워드 매칭으로만 부여
```

### `config/keywords.yaml`
```yaml
whitelist:
  공정_기술: ["EUV", "GAA", "수율", "패키징"]
  공급망: ["HBM", "웨이퍼", "파운드리 증설"]
  규제_무역: ["수출통제", "관세", "반도체법"]
  기업활동: ["M&A", "합작법인", "증설"]
  시장분석_투자의견: ["실적 전망", "투자의견"]   # 근거 있는 투자의견은 화이트리스트
blacklist:
  근거없는_시황: ["급등", "테마주", "찌라시"]
```

### `config/source_tiers.yaml`
```yaml
tier1_원출처: ["삼성전자 뉴스룸", "SK하이닉스 뉴스룸", "KIPRIS"]
tier2_전문지: ["디일렉", "EE Times"]
tier3_재인용: ["네이버뉴스 재배포"]
```

---

## 3. Gemini API 연동 스펙 (`gemini_client.py`)

- **모델**: `gemini-2.5-flash` (기본), `gemini-2.5-flash-lite` (고빈도 분류처럼 가벼운 작업)
- **인증**: `.env`의 `GEMINI_API_KEY`, `google-genai` SDK 사용
- **공통 규칙**: 모든 호출은 `response_mime_type="application/json"` + 스키마 지정으로 구조화 출력 강제 (파싱 실패 방지)
- **재시도**: 429/일시 오류 시 exponential backoff, 무료 티어 한도(분당 15~30회) 감안해 요청 간 최소 간격 적용
- **Step별 사용 모델**:
  | Step | 모델 | 이유 |
  |---|---|---|
  | 2. 중복 판정 | Flash-Lite | 단순 유사도 판정, 고빈도 |
  | 3. 분류 | Flash-Lite | 단순 분류 |
  | 4. 요약 | Flash | 문장 생성 품질 필요 |

---

## 4. 에러·알림 규칙 (`notify.py`)

| 상황 | 처리 |
|---|---|
| 설정 로드 실패 | 즉시 실행 중단 + 알림 |
| 특정 소스 3회 연속 재시도 실패 | 로그만 기록, 파이프라인 계속 진행 |
| 특정 소스 0건 연속 (7일 평균 대비) | 경고 알림 |
| Gemini API 요약 실패 | 헤드라인+링크 폴백, 파이프라인 계속 진행 |
| 08:30까지 미완료 | 실패 알림 발송("뉴스 없는 날"과 구분) |

---

## 5. 구현 지침

이 명세서를 기반으로 Claude Code에서 `src/` 모듈을 Step 순서대로 구현·테스트한다.
각 모듈은 독립 실행 가능하게 작성해 `main.py`에서 순차 호출하거나, 개발 중에는 Step별로 개별 테스트한다.
