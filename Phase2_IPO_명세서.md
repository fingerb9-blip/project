# 반도체 뉴스 데일리 브리핑 — Phase 2 IPO 명세서 (자동 스케줄링)

> 이 문서는 Phase 1(IPO_명세서.md)이 로컬에서 정상 동작한 뒤, GitHub Actions로 완전 자동화하기 위한 확장 명세다.
> Phase 1의 Step 0~6 로직 자체는 변경하지 않으며, 실행 환경·트리거·상태 관리·알림만 추가한다.

## 0. 목표와 전제

| 항목 | 내용 |
|---|---|
| 목표 | 매일 08:00 KST 자동 실행 → 08:30 발송, 사람 개입 없이 완전 자동화 |
| 전제 | Phase 1의 `src/`, `config/` 모듈이 로컬에서 정상 동작 확인됨 |
| 변경 범위 | 실행 트리거(cron→로컬 스케줄러→GitHub Actions), 인증(로컬 .env→GitHub Secrets), 상태 저장, 실패 알림 |
| 변경 없음 | Step 1~6 파이프라인 로직, config yaml 4종, Gemini API 호출 방식 |

---

## 1. Phase 1 대비 변경 사항 요약

| 구분 | Phase 1 | Phase 2 |
|---|---|---|
| 실행 위치 | 로컬 PC | GitHub Actions 러너(우분투) |
| 트리거 | 로컬 cron / 작업 스케줄러 | `schedule` cron (GitHub Actions) |
| 인증 관리 | `.env` 파일 | GitHub Secrets (`GEMINI_API_KEY`, `SMTP_USER`, `SMTP_APP_PASSWORD`) |
| 실행 이력 확인 | 로그 파일 육안 확인 | 상태 파일 커밋 + GitHub Actions 실행 기록 |
| 실패 인지 | 사람이 이메일 안 옴을 알아챔 | 자동 실패 알림(별도 채널) |
| 데이터 저장 | 로컬 `data/` 디렉토리 | 리포지토리에 커밋 또는 별도 스토리지(아래 3장 참고) |

---

## 2. GitHub Actions 워크플로우 스펙 (`.github/workflows/daily_briefing.yml`)

- **트리거**: `schedule: cron: "0 23 * * *"` (UTC 23:00 = KST 08:00), 수동 실행용 `workflow_dispatch` 병행
- **러너**: `ubuntu-latest`
- **Secrets**: 리포지토리 Settings → Secrets and variables → Actions 에 등록
  - `GEMINI_API_KEY`
  - `SMTP_USER`, `SMTP_APP_PASSWORD`
  - (선택) `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
- **주요 스텝**:
  1. `actions/checkout@v4`
  2. Python 환경 설정 (`actions/setup-python@v5`)
  3. 의존성 설치 (`pip install -r requirements.txt`)
  4. `main.py` 실행 (환경변수로 Secrets 주입)
  5. 실행 결과(`data/archive/*.md`, 상태 파일)를 리포지토리에 커밋 & 푸시
  6. 실패 시 `if: failure()` 조건으로 알림 스텝 실행

```yaml
name: daily-briefing
on:
  schedule:
    - cron: "0 23 * * *"
  workflow_dispatch: {}
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Run pipeline
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_APP_PASSWORD: ${{ secrets.SMTP_APP_PASSWORD }}
        run: python main.py
      - name: Commit state & archive
        if: success()
        run: |
          git config user.name "briefing-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/
          git commit -m "chore: daily run $(date +%F)" || echo "no changes"
          git push
      - name: Notify on failure
        if: failure()
        run: python src/notify.py --event pipeline_failed --run-id ${{ github.run_id }}
```

- **비용**: public 리포지토리는 Actions 무제한 무료, private 리포지토리는 월 2,000분 무료 한도 — 이 파이프라인은 실행당 수 분 내외라 한도 내에서 충분

---

## 3. 상태 저장 스펙 (`data/state/run_status.json`)

- **목적**: 중복 실행 방지, 마지막 성공 시각 추적, "뉴스 없는 날"과 "파이프라인 실패"를 구분
- **스키마**:
```json
{
  "last_run_date": "2026-07-08",
  "last_run_status": "success",
  "last_success_at": "2026-07-08T08:12:00+09:00",
  "steps_completed": ["collect", "dedup", "classify", "summarize", "assemble", "send"],
  "article_count": 42,
  "failed_sources": []
}
```
- **저장 방식**: Phase 2에서는 리포지토리 내 커밋(위 워크플로우의 "Commit state & archive" 스텝)으로 관리 — 별도 DB/스토리지 없이 Git 히스토리 자체가 실행 이력이 됨
- **활용**: Step 0(`step0_init.py`)에서 `last_run_date`가 오늘이면 중복 실행 방지(수동 트리거 실수 대비), `steps_completed`로 어느 단계까지 성공했는지 확인 가능

---

## 4. 실패 알림 스펙 (`notify.py` 확장)

| 실패 유형 | 감지 시점 | 알림 채널 |
|---|---|---|
| 워크플로우 자체 실패(러너 오류, 타임아웃) | GitHub Actions `if: failure()` | GitHub 기본 이메일 알림(리포지토리 소유자에게 자동 발송) + `notify.py` 보조 알림 |
| Step 1~6 중 특정 단계 실패 | `main.py` 내 예외 처리 | `notify.py`로 관리자 이메일 발송 — Phase 1과 동일 |
| 08:30까지 이메일 미발송 | 없음(수동 확인 필요) → Phase 2에서는 워크플로우 실행 자체가 실패하면 위 두 알림으로 대체 커버 |
| Secrets 만료/오인증 | SMTP/Gemini 호출 401/403 | `notify.py`로 "인증 오류 — Secrets 재확인 필요" 명시적 메시지 발송 |

- **원칙**: Phase 1의 "침묵 실패 방지"를 그대로 계승 — 실패는 반드시 사람에게 도달해야 하며, GitHub 기본 알림에만 의존하지 않고 이메일 알림을 이중화한다

---

## 5. 마이그레이션 체크리스트 (Phase 1 → Phase 2)

1. [ ] 로컬 `.env`의 값들을 GitHub Secrets로 이전
2. [ ] `requirements.txt` 최신화 및 러너 환경에서 설치 확인
3. [ ] `step0_init.py`에 상태 파일 읽기/중복 실행 방지 로직 추가
4. [ ] 워크플로우 파일 추가 후 `workflow_dispatch`로 수동 트리거 테스트 최소 3회
5. [ ] 실패 알림이 실제로 오는지 의도적 실패(예: 잘못된 API 키)로 검증
6. [ ] cron이 KST 08:00에 정확히 맞는지 UTC 변환 재확인(서머타임 없음, 단순 -9h 고정이므로 리스크 낮음)
7. [ ] 안정화 기간(최소 1~2주) 동안 로컬 스케줄러와 병행 운영 후 완전 전환

---

## 6. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| GitHub Actions 러너 지연(스케줄 정시 실행 보장 안 됨, 수 분~수십 분 지연 가능) | 08:30 도착 목표를 08:00 실행 기준으로 30분 여유 확보. 지연이 잦으면 발송 목표 시각을 유연화하거나 알림 기준을 "실행 완료 후 30분 초과"로 조정 |
| private 리포지토리 전환 시 Actions 분당 과금 | 현재 무료 한도 내(월 2,000분)로 충분 — 사용량 급증 시에만 재검토 |
| 리포지토리에 데이터 커밋 누적으로 용량 증가 | 아카이브를 월별로 압축하거나 오래된 raw/dedup 중간 산출물은 주기적으로 정리 |
| Secrets 유출 위험 | 리포지토리를 private으로 유지, Secrets는 로그에 출력되지 않도록 코드에서 마스킹 확인 |
