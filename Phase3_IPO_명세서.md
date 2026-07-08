# 반도체 뉴스 데일리 브리핑 — Phase 3 IPO 명세서 (워치리스트 고도화)

> 이 문서는 Phase 1(MVP)·Phase 2(자동 스케줄링)가 안정 운영된 뒤 추가하는 확장 명세다.
> 기획안 4장의 "이상 신호 감지 & 즉시 속보 알림"(4-1)과 "이슈 지식그래프"(4-2) 두 기능을 다룬다.
> 권장 도입 순서: 4-1(이상 신호 감지) 최우선 → 4-2(이슈 지식그래프) 그다음. 4-3(경쟁 구도 레이더)은 Phase 4에서 별도 다룬다.
>
> **[수정] 전달 채널 변경 반영**: 이 문서는 브리핑 본문을 이메일로 발송하던 시점에 작성되어 "즉시 속보 이메일 발송"을 전제로 한다.
> 이후 전달 채널이 GitHub Pages 대시보드(본문) + Gmail SMTP(실패 알림 전용)로 바뀌었으므로, 아래 "즉시 속보"는
> **이메일이 아니라 대시보드 즉시 갱신·재배포**로 구현한다. 정식 반영본은 `docs/phase3_ipo.md` 참고.

## 0. 목표와 전제

| 항목 | 내용 |
|---|---|
| 목표 | ① 하루 1회 브리핑 구조를 유지하되 비정상 급증 이슈는 즉시 알림. ② 여러 날 이어지는 이슈를 파편적으로 반복 노출하지 않고 하나의 타임라인으로 관리 |
| 전제 | Phase 1~2의 Step 1~6 파이프라인이 매일 안정적으로 동작 중 |
| 변경 범위 | Step 1 결과를 시간 단위로 재사용하는 신규 배치(이상 신호 감지), Step 4~5 사이에 이슈 매칭 단계 삽입, 신규 데이터 저장소 2종, 브리핑 템플릿에 타임라인 섹션 추가 |
| 변경 없음 | Step 1(수집)~Step 3(분류) 자체 로직, config yaml 4종 |

---

## 1. Phase 1/2 대비 추가 사항 요약

| 구분 | Phase 1/2 | Phase 3 |
|---|---|---|
| 실행 빈도 | 하루 1회(08:00) | 하루 1회(정규) + **매시 정각(이상 신호 감지)** |
| 데이터 저장소 | `data/*/YYYY-MM-DD.json` | + `data/state/frequency_baseline.json`, `data/state/issues.json` |
| 알림 종류 | 실패 알림만 | + **속보 즉시 알림**(정상 상황) |
| 브리핑 구성 | ①핵심 ②카테고리별 ③확인필요 ④수집상태 | + **⑤ 진행 중 이슈 타임라인** 섹션 |
| GitHub Actions | 워크플로우 1개(daily) | + 워크플로우 1개 추가(hourly) |

---

## 2. 신규 데이터 저장소 스펙

### `data/state/frequency_baseline.json` — 키워드·기업별 언급 빈도 이동평균

```json
{
  "samsung_electronics": {
    "규제": { "hourly_avg_7d": [2.1, 1.8, 0.5, "...(24개, 시간대별)"] },
    "화재": { "hourly_avg_7d": [0.1, 0.0, 0.0, "...(24개)"] }
  }
}
```
- 매시 배치가 실행될 때마다 최근 7일 같은 시간대 평균으로 갱신(rolling update)
- Step 1(수집) 결과를 시간 단위로 재집계해서 채움 — 별도 수집 로직 불필요

### `data/state/issues.json` — 진행 중 이슈 타임라인

```json
{
  "issue_id": "sha1(entity+keyword+first_seen_date)",
  "entity": "SK하이닉스",
  "title": "청주 M15X 증설 관련 이슈",
  "first_seen": "2026-07-05",
  "last_updated": "2026-07-08",
  "status": "진행중",
  "related_article_ids": ["...", "..."],
  "progress_summary": "Gemini API가 생성한 경과 요약 문단 (3일 이상 지속 시에만 존재)"
}
```
- `status`: `진행중` | `종료`(7일 이상 신규 기사 없으면 자동 종료 처리)

---

## 3. 기능 A: 이상 신호 감지 & 즉시 속보 알림

### 목적
특정 이슈가 평소 대비 비정상적으로 급증하면 정규 08:30 브리핑을 기다리지 않고 즉시 알림을 보낸다. "침묵 실패"(못 거르는 리스크)의 반대편 리스크인 "속보를 다음 날 아침까지 놓치는 문제"를 해결한다.

### 신규 모듈: `src/step1_5_anomaly_detect.py` (매시 정각 실행)

- **Input**: 최근 1시간 신규 기사(Step 1 로직 재사용, 시간 범위만 다름), `data/state/frequency_baseline.json`
- **Process**:
  1. 최근 1시간 신규 기사 수집 (Step 1 함수 재사용)
  2. 등록 소스 전체 기준, 특정 기업명 + 위험 키워드(`규제`, `화재`, `셧다운`, `리콜` 등)의 언급 건수 집계
  3. 최근 7일 같은 시간대 평균 대비 **임계치(예: 3배) 초과** 여부 판정
  4. 임계치 초과 시 Gemini API로 "이 급증이 진짜 속보인지, 단순 재탕 보도인지" 사실관계 확인 및 `[확정]`/`[관측]` 판정
  5. `frequency_baseline.json` 갱신(rolling update)
- **Output**: 확정 속보 발생 시 `step5_assemble.py`의 대시보드 렌더 함수를 재사용해 `data/dashboard/index.html`에 속보 배너를 즉시 반영(재배포), `issues.json`에도 신규/기존 이슈로 반영
- **알림 억제 규칙**: 같은 이슈로 이미 속보 배너를 띄웠으면 **24시간 내 재갱신하지 않고** 정규 브리핑에서만 갱신 — 알림 피로 방지

### 트리거 조건 요약표

| 항목 | 내용 |
|---|---|
| 트리거 조건 | 특정 기업명 + 위험 키워드의 최근 1시간 언급 건수가 최근 7일 같은 시간대 평균 대비 3배 초과 |
| 필요한 데이터 | Step 1 결과 재사용 + `frequency_baseline.json`(신규) |
| 필요한 기술 | Python 통계 로직 + Gemini API 사실 확인 |
| 처리 흐름 | 수집(1h) → 빈도 집계 → 임계치 판정 → Gemini API 확인 → 확정 시 대시보드 즉시 재배포 |

---

## 4. 기능 B: 이슈 지식그래프 (반복 이슈 추적 & 경과 요약)

### 목적
여러 날에 걸쳐 보도되는 같은 이슈(예: 특정 기업의 증설·수율 이슈)를 매일 파편적인 개별 기사로 반복 노출하는 대신, 하나의 이슈 타임라인으로 묶어 관리한다. 3일 이상 지속되면 "경과 요약" 문단을 자동 생성해 매번 처음부터 맥락을 파악해야 하는 부담을 줄인다.

### 신규 모듈: `src/step4_5_issue_match.py` (Step 4 요약 이후, Step 5 조립 이전)

- **Input**: Step 4 요약 결과, `data/state/issues.json`
- **Process**:
  1. 매일 요약된 기사마다 기존 `issues.json`의 이슈 목록과 Gemini API로 의미 유사도 매칭 시도 (`company_aliases.yaml`로 기업명 정규화까지 함께 활용)
  2. 매칭되면 같은 `issue_id`로 연결(기사 추가, `last_updated` 갱신), 없으면 신규 이슈 생성
  3. 이슈가 3일 이상 이어지면(`first_seen` 기준) Gemini API로 "경과 요약" 한 문단 추가 생성
  4. 7일 이상 신규 기사가 없는 이슈는 `status: 종료`로 전환
- **Output**: 갱신된 `data/state/issues.json`, Step 5에 전달할 "진행 중 이슈" 목록

### 처리 흐름 요약표

| 항목 | 내용 |
|---|---|
| 필요한 기술 | Gemini API 의미 유사도 판정 + `company_aliases.yaml` 정규화 |
| 처리 흐름 | 이슈 매칭 시도 → 연결/신규 생성 → 타임라인 카드 생성 → 3일 이상 지속 시 경과 요약 추가 |
| 체감 효과 | 높음 — 브리핑 조립(맥락화) 단계의 실제 작업 부담을 줄여줌 |
| 권장 도입 시점 | 이상 신호 감지(기능 A) 다음, Phase 3 안정화와 병행 가능 |

---

## 5. 대시보드 변경 (`step5_assemble.py`)

기존 ①오늘의 핵심 ②카테고리별 ③확인 필요 목록 ④수집 상태에 **⑤ 진행 중 이슈 타임라인** 섹션을 추가하고,
`index.html` 상단에 **속보 배너 영역**을 추가한다.

```
⑤ 진행 중 이슈 (issues.json에서 status="진행중"인 항목)
- [SK하이닉스] 청주 M15X 증설 관련 이슈 (7/5~, 4일째)
  경과 요약: (3일 이상 지속 시 Gemini API 생성 문단)
  관련 기사: 3건 → 전체 보기 링크
```

- `index.html` 상단 배너 예시: `🚨 [SK하이닉스] OO 공장 화재 속보 (07:14 확정) → 상세 보기` — 기존 상태 배지 바로 아래 노출

---

## 6. 실행 스케줄 변경 (GitHub Actions)

기존 `daily_briefing.yml`(1일 1회)에 더해 신규 워크플로우 `.github/workflows/hourly_anomaly_check.yml` 추가:

```yaml
name: hourly-anomaly-check
on:
  schedule:
    - cron: "0 * * * *"   # 매시 정각(UTC 기준, KST와 무관하게 24회/일)
  workflow_dispatch: {}

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Run anomaly detection
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python src/step1_5_anomaly_detect.py
      - name: Commit state & dashboard
        if: success()
        run: |
          git config user.name "briefing-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/state data/dashboard
          git commit -m "chore: hourly anomaly check $(date -u +%FT%H)" || echo "no changes"
          git fetch origin main
          git rebase origin/main
          git push
      - name: Upload dashboard artifact
        if: success()
        uses: actions/upload-pages-artifact@v3
        with:
          path: data/dashboard
      - name: Deploy to GitHub Pages
        if: success()
        id: deployment
        uses: actions/deploy-pages@v4
      - name: Notify on failure
        if: failure()
        env:
          SMTP_HOST: smtp.gmail.com
          SMTP_PORT: "587"
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_APP_PASSWORD }}
          SMTP_TO: ${{ secrets.SMTP_TO }}
        run: python src/notify.py --event pipeline_failed --run-id ${{ github.run_id }}
```

- 이메일(SMTP)은 이 워크플로우 자체가 실패했을 때만 사용한다(파이프라인 실패 알림 전용). 속보 콘텐츠 전달은 항상 대시보드 재배포로 처리한다.

- **Gemini 무료 티어 영향**: 매시 실행이 추가되므로 호출량이 하루 24회(빈도 집계용, 실제 Gemini 호출은 임계치 초과 시에만) 늘어나지만, 이상 신호가 실제로 자주 발생하지 않는 한 무료 티어 한도(하루 약 1,500회) 내에서 충분히 여유 있음

---

## 7. 도입 순서 및 마이그레이션 체크리스트

1. [ ] `frequency_baseline.json` 초기값 생성 — 최근 7일치 데이터를 소급 집계해서 채워둠(콜드 스타트 시 오탐 방지)
2. [ ] 기능 A(이상 신호 감지)부터 단독 배포, 최소 1주일 운영하며 임계치(3배) 튜닝
3. [ ] 알림 억제 규칙(24시간)이 실제로 동작하는지 의도적 반복 이슈로 테스트
4. [ ] 기능 A 안정화 후 기능 B(이슈 지식그래프) 배포
5. [ ] `issues.json` 매칭 정확도를 1주일간 사람이 표본 검토(2-2절 "도메인 감각 퇴화" 대응 설계와 동일한 방식)
6. [ ] 브리핑 템플릿에 ⑤ 진행 중 이슈 섹션이 정상 렌더링되는지 확인
7. [ ] hourly 워크플로우의 GitHub Actions 사용량(분) 모니터링

---

## 8. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| 콜드 스타트 시 baseline 데이터 부족 → 오탐(false positive) 급증 | 최소 7일치 소급 데이터로 초기화, 초기 1주는 알림 대신 로그만 기록하는 "관찰 모드"로 운영 |
| 이슈 매칭 오판(다른 사건을 같은 이슈로 묶거나, 같은 이슈를 분리) | 주 1회 표본 검토로 매칭 정확도 점검, 필요 시 유사도 임계치 조정 |
| hourly 워크플로우로 GitHub Actions 무료 한도 소진(private repo) | public repo 유지 시 무제한이므로 영향 없음. private 전환 시에는 사용량 모니터링 필수 |
| 알림 피로(속보 배너가 너무 자주 뜸) | 24시간 억제 규칙 + 임계치 상향 조정으로 대응 |
| 매시 Pages 재배포로 배포 이력 과다 | 임계치 초과(속보 확정) 시에만 커밋·배포, 평시엔 상태 파일만 갱신하고 커밋 스킵 |
