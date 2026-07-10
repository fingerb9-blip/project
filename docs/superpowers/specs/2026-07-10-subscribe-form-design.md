# 자동 구독 폼 — 설계 (구글 폼 · 서버리스)

> 작성일: 2026-07-10 · 상태: 설계 승인됨
> 이메일 뉴스레터(Step 7, `docs/superpowers/specs/2026-07-10-email-newsletter-design.md`)의 후속.
> 코어 파이프라인 변경 없이 구독자 명단 소스만 확장한다.

## 1. 목표와 범위

| 항목 | 내용 |
|---|---|
| 목표 | 방문자가 대시보드에서 이메일을 입력·제출하면 자동으로 구독 명단에 등록되고, 다음 뉴스레터 발송(Step 7)에 자동 반영된다. |
| 제약 | 정적 GitHub Pages라 서버가 없다. 구글이 폼·저장(시트)을 호스팅하고, 파이프라인(GitHub Actions)이 게시된 CSV를 HTTP로 읽기만 한다. 우리 쪽 서버 0. 무료. |
| 규모 | 지인 소수(10명대). |

### 데이터 흐름
```
방문자 → 대시보드의 구글 폼(iframe)에 이메일+동의 제출
  → 구글 시트(소유자 계정)에 자동 저장
  → 시트를 "웹에 CSV로 게시" (URL 1개)
  → 매일 파이프라인이 CSV를 HTTP GET으로 읽어 이메일 추출
  → 기존 SUBSCRIBERS(env, 수동) 명단과 합쳐(∪) 중복 제거 후 발송
```

### 포함
- 대시보드 `index.html`에 구독 폼(iframe) 섹션 추가
- 파이프라인이 게시 CSV에서 이메일을 읽어 기존 명단과 병합
- CSV 실패 시 env 명단으로 폴백

### 제외 (YAGNI / 무료·소규모)
- 자체 서버/백엔드, 결제, 로그인, 구독 취소 자동화(취소는 기존대로 "메일 회신" → 소유자가 시트에서 수동 삭제)
- 폼의 이름 필드(이메일 + 수신동의 체크만)
- 완전 비공개 저장(게시 CSV의 URL-공개 노출을 감수. 필요 시 후속으로 앱스스크립트 교체)

## 2. 대시보드 변경 (`src/step5_assemble.py`)

- `build_index_html`에 "뉴스레터 구독" 섹션 추가. 환경변수 `SUBSCRIBE_FORM_URL`이 있으면 그 URL을 `src`로 하는 `<iframe>`을 렌더하고, 없으면 섹션을 통째로 생략한다.
- URL은 `_esc()`로 이스케이프해서 삽입한다. iframe에는 title/폭 등 최소 속성만 둔다.
- `build_index_html`에 `subscribe_form_url: str | None = None` 파라미터를 추가하고, `main.py`가 `os.environ.get("SUBSCRIBE_FORM_URL")`를 넘긴다(기존 호출부 2곳 — 성공/실패 경로 모두 전달).

## 3. 파이프라인 변경 (`src/step7_subscriber_email.py`)

- 신규 `fetch_csv_subscribers(csv_url: str | None = None) -> list[str]`:
  - `csv_url`이 None이면 `os.environ.get("SUBSCRIBERS_CSV_URL", "")`를 사용. 비어 있으면 `[]`.
  - `urllib.request`로 CSV를 GET(타임아웃 10초), `csv` 모듈로 파싱.
  - **열 위치에 의존하지 않는다**: 모든 셀을 훑어 이메일처럼 보이는 값(`@` 포함 + `.` 포함)만 수집한다(구글 폼 응답 시트의 타임스탬프·동의 열을 자연히 배제).
  - `@` 검증·중복 제거(입력 순서 유지). 어떤 예외(네트워크·파싱)도 잡아 `[]` 반환 + 로그(폴백).
- 신규 `gather_subscribers() -> list[str]`: `load_subscribers()`(env) 와 `fetch_csv_subscribers()`(CSV)를 합쳐 중복 제거(입력 순서 유지, env 먼저).
- `run(...)`의 `subscribers is None` 분기를 `load_subscribers()` → `gather_subscribers()`로 교체. 나머지 발송·중복가드·상태 로직은 그대로.

## 4. 설정·보안

- 신규 환경변수(GitHub Actions Secret) 2개:
  - `SUBSCRIBE_FORM_URL` — 구글 폼 임베드 URL (대시보드 iframe용)
  - `SUBSCRIBERS_CSV_URL` — 게시된 응답 시트 CSV URL (명단 읽기용)
- 워크플로 `Run pipeline` env에 위 2개 추가.
- ⚠️ 게시 CSV는 URL을 아는 사람은 볼 수 있다 → URL을 시크릿으로만 관리(소규모라 위험 낮음). 이메일은 **repo에 커밋되지 않는다**(구글 시트에만 존재).
- 구글 폼에 "수신 동의" 체크박스 + 이메일 필드 → 폼 제출이 곧 opt-in.

## 5. 에러 처리·엣지

| 상황 | 처리 |
|---|---|
| CSV 읽기 실패(네트워크/구글 장애) | `fetch_csv_subscribers`가 `[]` 반환 → env 명단으로 폴백, 로그만, 발송 계속 |
| `SUBSCRIBERS_CSV_URL` 미설정 | CSV 소스 없이 env 명단만 사용 |
| `SUBSCRIBE_FORM_URL` 미설정 | 대시보드 구독 섹션 생략 |
| 폼 응답에 중복·오타 이메일 | `@` 검증으로 오타 일부 배제, 중복 제거 |
| 구독 취소 | 소유자가 시트에서 수동 삭제(소규모) |

## 6. 테스트 (네트워크 mock)

- `fetch_csv_subscribers`: CSV 텍스트에서 이메일만 추출(타임스탬프·동의 열 제외), 중복 제거, `@` 필터; fetch 예외 → `[]`; 빈 URL → `[]`.
- `gather_subscribers`: env ∪ CSV 병합·중복 제거(env 우선 순서).
- `run`: `subscribers=None`일 때 `gather_subscribers` 경로를 타는지(CSV+env 병합분에게 발송).
- `build_index_html`: `SUBSCRIBE_FORM_URL` 있으면 iframe(이스케이프된 URL) 포함, 없으면 구독 섹션 미포함.

## 7. 사용자 셋업 (구현 후, 코드 밖)

1. 구글 폼 생성: 질문 = 이메일(단답), "뉴스레터 수신에 동의합니다"(체크박스). 응답 → 시트 자동 연결.
2. 응답 시트 → 파일 → 공유 → **웹에 게시 → 쉼표로 구분된 값(.csv)** → URL 복사.
3. 폼 → 보내기 → `< >`(임베드) → iframe `src` URL 복사.
4. GitHub Secret 2개 등록: `SUBSCRIBE_FORM_URL`, `SUBSCRIBERS_CSV_URL`.
