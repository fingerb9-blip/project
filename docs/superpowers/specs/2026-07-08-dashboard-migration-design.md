# 브리핑 전달 채널: 이메일 → GitHub Pages 대시보드 전환 설계

> 작성일: 2026-07-08
> 배경: Phase 1 MVP가 GitHub Actions로 매일 자동 실행되며 Gmail SMTP로 브리핑 이메일을 발송 중.
> 브리핑 "본문"을 이메일 대신 대시보드(웹페이지)로 확인하고 싶다는 요청에 따른 전환 설계.

## 범위

- **바꾸는 것**: 매일 발송되던 브리핑 "본문" 전달 채널 — Gmail SMTP 이메일 → GitHub Pages 정적 대시보드
- **바꾸지 않는 것**:
  - 실패 알림(`notify.py`가 보내는 관리자 이메일 — 설정 로드 실패, 인증 오류, 파이프라인 실행 실패)은 그대로 이메일 유지
  - Step 0~4(수집·중복제거·분류·요약) 로직 전체
  - `data/archive/YYYY-MM-DD.md` 아카이브 (그대로 유지, 대시보드와 별개로 계속 생성)

## 확정된 결정 사항

| 항목 | 결정 |
|---|---|
| 대체 범위 | 브리핑 본문만 대시보드로. 실패 알림은 이메일 유지 |
| 호스팅 | GitHub Pages 정적 사이트 (기존 GitHub Actions 파이프라인에 배포 스텝만 추가) |
| 공개 범위 | 공개 URL로 진행 (링크를 아는 사람은 누구나 접근 가능함을 인지하고 동의) |
| 이력 범위 | 오늘자 브리핑 + 과거 날짜 목록 탐색 가능 (`data/archive` 기존 데이터 재사용) |
| 시각 수준 | 카드/섹션 레이아웃, 텍스트 중심 (차트/그래프 없음) |
| 생성 아키텍처 | Step 5(조립)를 확장해 날짜별 HTML도 함께 생성 + index 목록 갱신. 새 Step 신설 안 함 |

## 아키텍처

### 데이터 흐름

```
Step 1~4 (변경 없음)
  ↓
Step 5 (조립, 확장)
  ├─ data/archive/YYYY-MM-DD.md      (기존 유지 — 원본 텍스트 아카이브)
  ├─ data/dashboard/YYYY-MM-DD.html  (신규 — 오늘자 카드형 브리핑 페이지)
  └─ data/dashboard/index.html       (신규 — 날짜별 목록 + 실행 상태 배지, 매 실행마다 갱신)
  ↓
Step 6 (발송·저장 → 저장 확인으로 축소)
  ├─ 이메일 발송 로직 제거
  └─ data/dashboard/ 산출물 존재 확인. 실패 시 기존과 동일하게 notify.notify_failure() 호출
  ↓
GitHub Actions
  ├─ Commit state & archive 스텝: data/dashboard 도 커밋 대상에 포함
  └─ (신규) Pages 배포 스텝: upload-pages-artifact + deploy-pages, path: data/dashboard/
```

### 페이지 구성

**`data/dashboard/YYYY-MM-DD.html`** — 기존 이메일/md의 4개 섹션을 카드형으로:
1. 오늘의 핵심 — 기사 카드(제목, `[확정]`/`[관측]` 태그, 요약, 원문 링크, 출처)
2. 카테고리별 — 섹션 헤더 + 기사 리스트
3. 확인 필요 — 링크 리스트
4. 수집 상태 — 테이블(소스 / 오늘 건수 / 최근 7일 평균), 오늘 건수가 평균 대비 크게 낮으면 경고 배지

**`data/dashboard/index.html`**:
- 최신 날짜 브리핑으로 바로 연결되는 카드
- 과거 날짜 목록 (최신순, `data/archive/*.md` 파일 목록 기반)
- 상단에 `data/state/run_status.json` 기반 마지막 실행 상태 배지(성공/실패, 마지막 성공 시각) — "침묵 실패 방지" 원칙을 대시보드에도 반영

스타일은 순수 HTML/CSS(인라인 또는 단일 stylesheet)로 처리. 클라이언트 사이드 JS·프레임워크·라우팅 없이 정적 링크 기반 내비게이션만 사용.

## 모듈별 변경 사항

### `src/step5_assemble.py`
- 기존 `build_briefing()`(마크다운 생성)은 그대로 유지
- 신규 함수 추가: 동일한 입력(`summarized_articles`, `pending_review_articles`, `collection_stats`)으로 날짜별 HTML을 생성하는 함수
- 신규 함수 추가: `data/archive/` 디렉토리를 스캔해 전체 날짜 목록 + `run_status.json`을 읽어 `index.html`을 생성하는 함수
- `run()`이 md 저장에 더해 위 두 HTML 파일도 `data/dashboard/`에 저장하도록 확장
- 대시보드 생성 코드는 기사 데이터·통계만 사용하며 환경변수나 Secrets를 참조하지 않음 (보안 원칙 명시)

### `src/step6_send.py`
- SMTP 이메일 발송 로직(`send_email`) 제거
- `run()`을 "대시보드 산출물 존재 확인"으로 재정의: `data/dashboard/YYYY-MM-DD.html`과 `index.html`이 정상 생성됐는지 확인
- 실패 시 기존과 동일하게 `notify.notify_failure("08:30까지 대시보드 미갱신", ...)` 형태로 알림 (문구만 "발송" → "갱신"으로 조정, 침묵 실패 방지 원칙 유지)

### `main.py`
- Step 6 호출부의 `smtp_config` 전달을 제거하고 대시보드 경로만 전달하도록 변경
- 실패 시 예외 처리·`run_status.json` 저장·`notify.py` 호출 로직은 변경 없음

### `.github/workflows/daily_briefing.yml`
- `permissions`에 `pages: write`, `id-token: write` 추가
- `Commit state & archive` 스텝의 `git add` 대상에 `data/dashboard` 추가
- 신규 스텝: `actions/upload-pages-artifact@v3` (path: `data/dashboard`) → `actions/deploy-pages@v4`
- 기존 `Notify on failure` 스텝(SMTP 기반 관리자 알림)은 변경 없음

### 사용자가 직접 해야 할 작업 (자동화 불가)
- GitHub 리포지토리 Settings → Pages → Source를 "GitHub Actions"로 변경 (웹 UI에서 1회 설정)

## 문서 갱신

- `CLAUDE.md`의 "전달 채널" 항목: `Gmail SMTP (앱 비밀번호, 무료)` → `GitHub Pages 대시보드 (본문) + Gmail SMTP (실패 알림 전용)`
- `docs/phase1_ipo.md`의 Step 5/Step 6 설명을 위 변경 사항에 맞게 수정

## 테스트 계획

- 로컬에서 `python main.py` 실행 후 `data/dashboard/index.html`, `data/dashboard/YYYY-MM-DD.html`을 브라우저로 열어 4개 섹션 렌더링과 과거 날짜 링크 확인
- `data/archive/`에 있는 기존 날짜 데이터로 `index.html`의 날짜 목록이 올바르게 생성되는지 확인
- Step 6가 대시보드 파일 누락 상황(의도적으로 산출물 삭제 후 재실행)에서 실패 알림을 정상적으로 트리거하는지 확인
- GitHub Actions에서 `workflow_dispatch`로 수동 트리거 후, Pages Source를 "GitHub Actions"로 설정한 뒤 배포된 URL 접속 확인
