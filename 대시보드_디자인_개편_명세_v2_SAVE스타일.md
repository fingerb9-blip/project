# 반도체 뉴스 브리핑 대시보드 — 디자인 개편 명세 v2 (SAVE 스타일)

> Claude Code에 붙여넣어 작업을 지시하기 위한 **디자인 개편 브리프**다.
> 목표: 업로드한 "SAVE" 앱 3개 화면의 비주얼 언어(보라·인디고 포인트, 흰 라운드 카드, 컬러 소스 배지, pill 필터, 히어로 배너, 북마크)를 **현재 파이프라인이 만드는 정적 대시보드**에 적용하고, 인덱스·데일리·과거·미래 페이지를 하나의 디자인으로 통일한다.
> 대상 파일: `src/step5_assemble.py`(전부 여기서 렌더링됨). 산출물: `data/dashboard/*.html`, `data/dashboard/style.css`.

---

## 0. 먼저 — 무엇이 매핑되고 무엇이 스코프 밖인가

레퍼런스는 네이티브 모바일 앱 목업이지만, 이 프로젝트는 **로그인·서버 없는 정적 사이트**다. 그래서 "비주얼 스타일"은 그대로 가져오되, 백엔드가 필요한 기능은 정직하게 구분한다.

**그대로 적용 가능 (이 명세의 범위)**
- 히어로 배너(이미지 3 "오늘의 데일리 리포트") → **인덱스 최상단 최신 브리핑 배너**
- 리포트 카드(날짜 + "리포트 읽기") → **인덱스 아카이브 리스트**
- 뉴스 피드 카드(컬러 소스 배지 + 태그 칩 + 제목 + 메타)(이미지 1) → **데일리 브리핑 기사 카드**
- pill 카테고리 필터(전체/종합/속보…) → 데일리 **카테고리 필터**(전체/메모리/장비·소재/팹리스·설계/규제·정책)
- 상단 검색바 → 현재 페이지 기사 **클라이언트 필터**(간단) / 아카이브 전체 검색(선택, §7)
- 컬러 소스 배지·태그 칩·라운드 카드·자유 게시판 목업의 드롭다운 필터 룩

**스코프 밖 또는 백엔드 필요 (이번엔 넣지 않거나 "선택"으로 표시)**
- **커뮤니티 게시판(이미지 2)** — 유저 글쓰기·인기글은 서버/DB가 있어야 하는 별개 제품. 이번 대시보드 개편엔 포함하지 않는다(비주얼 패턴만 차용).
- **조회수(조회수 8.5K)** — 분석 백엔드 필요. 정적 사이트엔 값이 없으므로 **표시하지 않는다**(넣으려면 GA 등 별도 연동).
- **알림 벨** — 푸시 백엔드 없음. 아이콘은 장식이거나 생략(권장: 생략).
- **PDF 다운로드** — 현재는 md/HTML만 생성. PDF는 **선택**(별도 생성 스텝 필요, §6-E).
- **북마크(SAVE)** — 로그인 없이는 브라우저 `localStorage` 기반 클라이언트 저장만 가능. **선택**(§6-F).

> 이 명세는 위 "적용 가능" 항목만 구현 대상으로 삼는다. "선택" 항목은 각 절에 방법만 적어두고 기본은 끈다.

---

## 1. 핵심 원칙 (v1에서 유지)

- **단일 템플릿 · 단일 스타일시트.** 디자인은 `build_dashboard_html()`, `build_index_html()`, `_DASHBOARD_CSS` 세 곳에서만 산다. 페이지별 인라인 스타일 금지.
- **모바일 퍼스트.** 레퍼런스가 폰 화면이므로 세로 1열 카드 레이아웃을 기본으로, 넓은 화면에서는 중앙 정렬 단일 컬럼(최대 폭 약 560px)로 유지한다.
- **점진적 향상.** JS는 필터 토글·검색 정도의 바닐라 JS만. 없어도 전 기사 표시. 빌드 스텝·프레임워크·유료 의존성 없음(GitHub Pages 유지).
- **보안 불변식.** 렌더링 시 `_esc()`(HTML 이스케이프)·`_safe_url()`(http/https만) 호출을 **절대 우회하지 않는다.** RSS/뉴스 텍스트는 신뢰 불가 입력.
- **접근성 하한선.** 키보드 포커스 링, `prefers-reduced-motion` 존중, 색만으로 의미 전달 금지(칩은 색+텍스트 병행).

---

## 2. 통일 메커니즘 (가장 중요 — v1에서 유지)

"7/9만 예뻐 보이는" 문제의 진짜 원인과 해법:

1. **모든 페이지가 `data/dashboard/style.css` 하나를 공유**한다(각 HTML이 `<link ... style.css>`로 참조, 매 실행 시 `_DASHBOARD_CSS`에서 재작성). → **CSS로 표현되는 변화(색·타이포·카드·칩·배너 룩)는 7/8까지 자동 통일**된다.
2. 단, 날짜별 페이지는 **정적 파일**이라 `build_dashboard_html()`이 만든 뒤 다시 안 만들어진다(`main.py`가 같은 날 재실행을 `DuplicateRunError`로 건너뜀). → **새 구조 요소(소스 배지·태그 칩·필터·히어로)는 CSS만으로 과거 페이지에 못 붙는다. 과거 페이지를 재생성(backfill)** 해야 한다(§8).
3. 지금 7/8과 7/9의 차이는 디자인이 아니라 **데이터**(7/8은 요약 실패라 링크만, 7/9는 요약·태그 있음)일 뿐, 클래스·구조는 동일하다.

---

## 3. 디자인 토큰 (레퍼런스에서 추출)

방향성: **밝고 부드러운 핀테크·뉴스 앱 톤.** 보라/인디고 포인트 + 흰 라운드 카드 + 컬러 소스 배지.

### 3-1. 색

```css
:root{
  --paper:#F5F6F8;      /* 앱 배경: 아주 옅은 쿨그레이 */
  --surface:#FFFFFF;    /* 카드 */
  --ink:#1A1D24;        /* 제목/본문 */
  --ink-soft:#8A909C;   /* 메타·타임스탬프·placeholder */
  --line:#ECEEF2;       /* 헤어라인 */

  --brand:#6C5CE7;      /* 히어로 배너·브랜드 포인트(보라) */
  --brand-2:#8E7DF5;    /* 배너 그라디언트 밝은 끝 */
  --action:#3D6FE6;     /* 링크·"리포트 읽기"·검색·북마크 활성(블루) */
  --pill-active:#14161B;/* 활성 필터 pill(검정) */

  /* 확인 태그(의미색) */
  --confirmed:#2E9E5B;  /* [확정] */
  --observed:#C9821A;   /* [관측] */
  --muted:#6B7280;      /* 요약 없음 */
  --warn-bg:#FFF6E5; --warn-line:#F0C36D;
}
```

### 3-2. 소스별 배지 색 (레퍼런스의 컬러 소스 배지)

각 소스에 고정 색을 배정한다(연한 배경 + 진한 텍스트, pill).

| 소스 | 배경 | 텍스트 |
|---|---|---|
| 삼성전자 뉴스룸 | `#ECEBFB` | `#5B4FC4` (보라) |
| SK하이닉스 뉴스룸 | `#E4F0FB` | `#2C6BB5` (블루) |
| 디일렉 | `#E1F1EF` | `#1F7A6B` (틸) |
| EE Times | `#FDE9DD` | `#C2652A` (오렌지) |
| 전자신문 | `#FDF1D6` | `#A9790B` (앰버) |
| ZDNet Korea | `#E7F2E6` | `#3B8B4E` (그린) |
| (미지정/기타) | `#EEF0F3` | `#5A6472` (그레이) |

### 3-3. 타이포그래피
- 본문·제목: `Pretendard`(무료·한글 최적) + 시스템 폴백. CDN 로드.
- 데이터/메타(타임스탬프·소스명 보조): 필요 시 `--font-mono`. 레퍼런스는 대부분 산세리프이므로 mono는 최소화.
- 스케일: 히어로 배너 1.05rem(600) / 카드 제목 1.0rem(700, 2줄 클램프) / 본문 0.9rem(1.6) / 메타 0.78rem(`--ink-soft`).

### 3-4. 여백·모서리
- 카드 radius **16px**, 검색바 12px, 히어로 배너 16px, 모든 칩/배지/필터 pill **999px**.
- 카드 패딩 14–16px, 카드 간격 10–12px. 컨테이너 좌우 패딩 16px, 최대 폭 560px 중앙 정렬.

### 3-5. 브랜드 마크
레퍼런스의 검은 스티커형 "SAVE" 로고처럼, **자체 워드마크**(예: `반도체브리핑` 또는 축약)를 살짝 기울인 검정 스티커 태그로. (남의 "SAVE" 로고를 그대로 쓰지 말 것.)

---

## 4. 컴포넌트 명세

### 4-1. 헤더 (전 페이지 공통)
- 좌: 브랜드 스티커 태그. 우: (알림 벨은 기본 생략).
- 아래: **검색바** — 라운드, 옅은 보더, placeholder `뉴스 태그·제목·내용을 검색해 주세요`, 우측 `--action` 색 돋보기 아이콘. 동작은 §4-3.

### 4-2. 섹션 탭 (선택)
레퍼런스 상단 탭(전체/뉴스원별). 이 프로젝트는 소스가 6종뿐이라 **기본은 생략**하고 §4-4 카테고리 필터만 둔다. 원하면 소스별 탭으로 확장(가로 스크롤, 활성 밑줄).

### 4-3. 검색바 동작
- 최소: 현재 페이지 카드에 대한 **클라이언트 필터**(제목·요약·소스·칩 텍스트 매칭, 바닐라 JS). JS 없으면 전 카드 표시.
- 선택: 아카이브 전체 검색은 Pagefind/Lunr.js 정적 인덱스(§7).

### 4-4. 카테고리 필터 (pill)
- `전체`(기본 활성=검정 pill) + 카테고리들(메모리/장비·소재/팹리스·설계/규제·정책). 가로 스크롤, 활성 pill은 `--pill-active` 배경 흰 텍스트.
- 각 카드에 `data-categories`를 부여하고 클릭 시 매칭 카드만 표시(§9 JS). `aria-pressed` 토글.

### 4-5. 뉴스 카드 (데일리 — 이미지 1)
구조(위→아래):
1. **뱃지 행:** 소스 배지(§3-2 색) + 확인 태그 칩(`[확정]/[관측]/요약 없음`) + 카테고리 칩. 우측 끝에 타임스탬프(`--ink-soft`, 예: "오늘 08:30").
2. **제목:** 700, 2줄 클램프. 원문 있으면 `--ink`(링크는 카드 전체 또는 제목).
3. **요약:** 있으면 2–3줄 표시(`--ink-soft` 아님, `--ink` 유지, line-height 1.6). 없으면 생략.
4. **푸터 행:** 좌측 `원문 보기 ↗`(`--action`), 우측 **북마크 아이콘**(선택, §6-F). 조회수는 표시 안 함.
- 카드: 흰 배경, 16px radius, 보더 `1px var(--line)`, hover 시 미세 그림자.

### 4-6. 리포트 카드 (인덱스 — 이미지 3)
- 좌상단 `리포트` 회색 태그 칩 + 우측 타임스탬프(갱신 시각).
- 날짜 제목 700: `2026년 7월 9일 (수)`.
- 액션 행: `📄 리포트 읽기`(→ 해당 `YYYY-MM-DD.html`, `--action`) + `⬇ PDF 다운로드`(선택, §6-E). 아이콘은 Tabler/인라인 SVG.

### 4-7. 히어로 배너 (인덱스 상단 — 이미지 3)
- 보라 그라디언트(`--brand-2`→`--brand`), 라운드 16px, 흰 텍스트. 좌측 돋보기/리포트 아이콘 + `오늘의 데일리 리포트`. 클릭 시 최신 브리핑으로 이동.
- 하단에 상태 문구 한 줄(선택): `● 정상 · 마지막 성공 07-09 10:21`(침묵 실패 방지 원칙 유지, 실패 시 붉게).

### 4-8. 칩·배지 규칙
- 소스 배지: §3-2 색 pill.
- 확인 태그 칩: `[확정]` 초록 틴트 / `[관측]` 앰버 틴트 / `요약 없음` 회색 틴트 — 색 + 텍스트 라벨 병행.
- 카테고리 칩: 중립 회색 아웃라인 pill. 다중 카테고리면 여러 개.
- 태그 칩 접두사 스타일(선택): 레퍼런스처럼 `# 속보`, 종목형 `$ 삼성전자` 표기 차용 가능.

---

## 5. 페이지 레이아웃

### 5-1. 인덱스 `index.html` (이미지 3 스타일 = 리포트 리스트)
```
[헤더: 브랜드 · 검색바]
┌── 히어로 배너 (보라) ────────────────┐
│  🔍 오늘의 데일리 리포트               │
│  ● 정상 · 마지막 성공 07-09 10:21     │
└──────────────────────────────────┘
[리포트 카드]
  [리포트]                       10:21 갱신
  2026년 7월 9일 (수)
  📄 리포트 읽기    ⬇ PDF 다운로드(선택)
[리포트 카드]
  [리포트]                       …
  2026년 7월 8일 (화)
  📄 리포트 읽기
  …
```

### 5-2. 데일리 `YYYY-MM-DD.html` (이미지 1 스타일 = 뉴스 피드)
```
[헤더: 브랜드 · 검색바]
[← 전체 목록]   [YYYY-MM-DD ▾ (선택)]
[ 전체 · 메모리 · 장비·소재 · 팹리스·설계 · 규제·정책 ]  ← pill 필터
오늘의 핵심
[뉴스 카드] 소스배지 [확정] 카테고리 · 08:30
           제목(2줄) / 요약 / 원문 보기 ↗   🔖
[뉴스 카드] …
확인 필요   → 간단 카드/리스트
수집 상태   → 표(숫자 우측정렬, 경고행 유지)
진행 중 이슈 → 카드
[푸터: 자동 생성 · 소스 6종]
```

---

## 6. 구현 지침 (`src/step5_assemble.py`)

### A. `_DASHBOARD_CSS` 교체
§3 토큰 + §9 참조 CSS로 교체. `<head>`에 `<meta name="viewport" content="width=device-width, initial-scale=1">` 추가.

### B. `build_dashboard_html()` 개편
- 헤더(브랜드+검색바) → 뒤로가기/날짜 내비(선택) → pill 필터 → "오늘의 핵심" 뉴스 카드 → 확인 필요 → 수집 상태 표 → 진행 중 이슈 → 푸터.
- 각 카드: 소스명→배지 클래스, 확인 태그→칩, 카테고리→`data-categories`+칩. **`_esc()`/`_safe_url()` 유지.**
- "오늘의 핵심" 컨테이너에 `id="feed"`(검색·필터 스코프). 카드에 `data-text`(소스+제목+요약 소문자)로 검색 매칭용 속성 부여.

### C. `build_index_html()` 개편
- 헤더 + 히어로 배너(최신 날짜로 링크, 상태 문구 포함) + 리포트 카드 리스트(날짜+요일, "리포트 읽기" 링크, PDF는 선택).

### D. 소스→배지 색 매핑
`step5_assemble.py`에 상수 dict로 두거나 `config/source_tiers.yaml`에 `badge` 필드를 추가해 로드. 미지정 소스는 그레이 폴백.

### E. (선택) PDF 다운로드
`리포트 읽기`는 그냥 그날 HTML 링크. `PDF 다운로드`를 넣으려면 assemble 단계에서 그날 브리핑을 PDF로 렌더하는 스텝이 필요(무료 라이브러리, 예: WeasyPrint로 HTML→PDF, 또는 reportlab). 링크는 `YYYY-MM-DD.pdf`. **기본은 끄고**, 넣을지 결정 후 별도 작업으로.

### F. (선택) 북마크
로그인 없으므로 브라우저 `localStorage` 기반 클라이언트 북마크만 가능. 카드 북마크 아이콘 토글 → 로컬 저장, "저장한 뉴스" 필터 제공. 실제 배포 사이트에선 동작하나 기기·브라우저 한정. **기본은 끄고 선택.**

### G. `build_alert_detail_html()`/속보 배너도 새 토큰·클래스에 정합.

### H. **스타일시트 재작성 보장**
`_DASHBOARD_CSS` 교체만으론 부족 — `data/dashboard/style.css`가 새 내용으로 덮여야 과거 페이지 룩이 즉시 통일된다. 파이프라인 재실행이 style.css를 다시 쓰지만, 데이터 없이 룩만 갱신하려면 §8 재생성 스크립트의 `--style-only`를 쓴다.

---

## 7. (선택) 아카이브 전체 검색
헤더 검색바를 "그날 카드 필터"를 넘어 **전체 아카이브 검색**으로 키우려면 Pagefind 또는 Lunr.js 정적 인덱스를 생성한다(빌드시 아카이브 HTML 인덱싱, 클라이언트에서 검색). 무료·정적. 이번 기본 범위에선 "현재 페이지 필터"까지만.

---

## 8. 과거 페이지 통일 (Backfill)
CSS 변화는 §6-H로 전 페이지에 반영되지만, **새 구조(소스 배지·태그 칩·필터·히어로·리포트 카드)는 이미 저장된 7/8 HTML엔 없다.** 과거 페이지를 새 템플릿으로 재렌더해야 한다.

`scripts/rebuild_dashboard.py`:
1. `data/summarized/*.json`(핵심)·`data/classified/*.json`("확인 필요")을 날짜별 순회.
2. `_compute_collection_stats` 재사용으로 수집 통계 계산.
3. `build_dashboard_html(..., all_dates=<전체>, updated_at=<mtime>)`로 `YYYY-MM-DD.html` 재생성.
4. 끝에 `build_index_html` + `style.css` 재작성.

```
python scripts/rebuild_dashboard.py            # 전체 재생성(7/8 포함)
python scripts/rebuild_dashboard.py --style-only   # 원천 데이터 없을 때: CSS·index만 갱신
```

**원천 데이터가 없을 때(현재 레포는 `data/summarized/` 등이 비어 있음):**
- 로컬에 날짜별 JSON이 있으면 완전 재생성.
- 없으면 `--style-only`로 색·타이포·카드 룩만 통일(소스 배지·칩·필터·히어로는 앞으로 생성되는 날짜부터). 
- 권장: 앞으로 `data/summarized/`·`data/classified/`를 삭제하지 말고 보관.

---

## 9. 참조 구현 — `_DASHBOARD_CSS` (SAVE 스타일, 모바일 퍼스트)

```css
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css");
:root{
  --paper:#F5F6F8; --surface:#FFF; --ink:#1A1D24; --ink-soft:#8A909C; --line:#ECEEF2;
  --brand:#6C5CE7; --brand-2:#8E7DF5; --action:#3D6FE6; --pill-active:#14161B;
  --confirmed:#2E9E5B; --observed:#C9821A; --muted:#6B7280; --warn-bg:#FFF6E5; --warn-line:#F0C36D;
  --font-sans:"Pretendard",-apple-system,"Segoe UI","Apple SD Gothic Neo",sans-serif;
}
*{box-sizing:border-box}
body{font-family:var(--font-sans);max-width:560px;margin:0 auto;padding:16px 16px 56px;
  color:var(--ink);background:var(--paper);line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--action);text-decoration:none}
a:hover{text-decoration:underline}

/* 헤더 */
.appbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.brand{display:inline-block;background:#14161B;color:#fff;font-weight:700;font-size:.85rem;
  padding:4px 10px;border-radius:6px;transform:skew(-6deg)}
.search{display:flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line);
  border-radius:12px;padding:11px 14px;margin-bottom:16px}
.search input{border:0;outline:0;flex:1;font-family:inherit;font-size:.9rem;background:transparent;color:var(--ink)}
.search input::placeholder{color:var(--ink-soft)}
.search .i{color:var(--action)}

/* pill 필터 */
.filter{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;margin:0 0 14px}
.filter button{flex:0 0 auto;font-family:inherit;font-size:.85rem;color:var(--ink-soft);
  background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:7px 15px;cursor:pointer}
.filter button[aria-pressed="true"]{background:var(--pill-active);color:#fff;border-color:var(--pill-active)}

/* 히어로 배너 */
.hero{background:linear-gradient(100deg,var(--brand-2),var(--brand));color:#fff;
  border-radius:16px;padding:18px 20px;margin:0 0 18px}
.hero h2{margin:0;font-size:1.05rem;font-weight:600;color:#fff;display:flex;align-items:center;gap:8px}
.hero .status{font-size:.8rem;opacity:.9;margin:.5rem 0 0}

/* 카드 공통 */
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
  padding:15px 16px;margin:0 0 11px;transition:box-shadow .15s}
.card:hover{box-shadow:0 4px 14px rgba(26,29,36,.06)}
.row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.spacer{flex:1}
.time{color:var(--ink-soft);font-size:.78rem}
.title{font-size:1rem;font-weight:700;line-height:1.4;margin:.55rem 0;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.summary{font-size:.9rem;color:var(--ink);margin:.35rem 0}
.cardfoot{display:flex;align-items:center;justify-content:space-between;margin-top:.5rem}
.cardfoot a{font-size:.85rem}
.bm{color:var(--ink-soft);cursor:pointer}.bm.on{color:var(--action)}

/* 배지·칩 */
.badge{font-size:.74rem;font-weight:600;padding:3px 9px;border-radius:999px;background:#EEF0F3;color:#5A6472}
.badge.s-samsung{background:#ECEBFB;color:#5B4FC4}
.badge.s-hynix{background:#E4F0FB;color:#2C6BB5}
.badge.s-thelec{background:#E1F1EF;color:#1F7A6B}
.badge.s-eetimes{background:#FDE9DD;color:#C2652A}
.badge.s-etnews{background:#FDF1D6;color:#A9790B}
.badge.s-zdnet{background:#E7F2E6;color:#3B8B4E}
.tag{font-size:.74rem;font-weight:600;padding:3px 9px;border-radius:999px}
.tag.ok{background:rgba(46,158,91,.12);color:var(--confirmed)}
.tag.obs{background:rgba(201,130,26,.14);color:var(--observed)}
.tag.mut{background:#EEF0F3;color:var(--muted)}
.chip{font-size:.74rem;color:var(--ink-soft);padding:3px 9px;border:1px solid var(--line);border-radius:999px}

/* 리포트 카드(인덱스) */
.report .datetitle{font-size:1.05rem;font-weight:700;margin:.5rem 0 .6rem}
.report .actions{display:flex;gap:18px}
.report .actions a{display:inline-flex;align-items:center;gap:6px;font-size:.9rem}

/* 표 */
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.85rem;background:var(--surface);border-radius:12px;overflow:hidden}
th,td{border-bottom:1px solid var(--line);padding:9px 11px;text-align:left}
th{background:#F1F3F6;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.warn td{background:var(--warn-bg)}

/* 섹션 제목·푸터 */
h2.sec{font-size:1.05rem;font-weight:700;margin:1.6rem 0 .7rem}
.alert-banner{background:#FDECEC;border:1px solid #F3B4B4;border-radius:14px;padding:12px 16px;margin:0 0 14px}
.site-footer{margin-top:2.4rem;padding-top:1rem;border-top:1px solid var(--line);font-size:.76rem;color:var(--ink-soft)}
:focus-visible{outline:2px solid var(--action);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
```

### 필터 + 검색 최소 JS (데일리 하단 인라인)
```html
<script>
function applyFilters(){
  var q=(document.getElementById('q')||{}).value||'';
  q=q.trim().toLowerCase();
  var active=document.querySelector('.filter button[aria-pressed="true"]');
  var cat=active?active.dataset.cat:'all';
  document.querySelectorAll('#feed .card').forEach(function(c){
    var okCat=(cat==='all')||((c.dataset.categories||'').split(' ').indexOf(cat)>-1);
    var okQ=!q||((c.dataset.text||'').indexOf(q)>-1);
    c.style.display=(okCat&&okQ)?'':'none';
  });
}
document.querySelectorAll('.filter button').forEach(function(b){
  b.addEventListener('click',function(){
    document.querySelectorAll('.filter button').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});
    applyFilters();
  });
});
var qi=document.getElementById('q'); if(qi) qi.addEventListener('input',applyFilters);
</script>
```
> JS 미동작 시 전 카드 표시 → 안전.

---

## 10. 완료 기준 체크리스트
- [ ] 인덱스가 보라 히어로 배너 + 리포트 카드(날짜+요일, "리포트 읽기")로 렌더된다.
- [ ] 데일리가 컬러 소스 배지 + 확인 태그 칩 + 카테고리 칩 + 2줄 제목 카드의 뉴스 피드로 렌더된다.
- [ ] `2026-07-09.html`과 `2026-07-08.html`이 육안상 동일한 디자인 시스템을 쓴다.
- [ ] pill 카테고리 필터와 검색바 필터가 동작한다(JS 꺼도 전 기사 표시).
- [ ] 6개 소스가 각기 다른 배지 색으로 구분된다(미지정=그레이).
- [ ] 조회수·알림 등 백엔드 필요 요소는 표시되지 않는다(스코프 준수).
- [ ] 모바일 폭에서 1열로 깔끔하고, 표는 가로 스크롤된다.
- [ ] `_esc()`/`_safe_url()` 호출이 하나도 제거되지 않았다.
- [ ] `python scripts/rebuild_dashboard.py`로 과거 페이지를 새 디자인으로 재생성할 수 있다.
- [ ] `tests/test_step5_assemble.py`가 새 구조에 맞게 통과한다.

---

### 부록 — Claude Code 한 줄 지시 예시
> `대시보드_디자인_개편_명세_v2_SAVE스타일.md`를 읽고 §3 토큰과 §9 CSS 기준으로 `src/step5_assemble.py`의 `_DASHBOARD_CSS`·`build_dashboard_html`·`build_index_html`을 SAVE 스타일(보라 히어로 배너·컬러 소스 배지·라운드 카드·pill 필터·모바일 퍼스트)로 개편해줘. §0 스코프를 지켜서 조회수·알림·커뮤니티·PDF·북마크는 넣지 말고, 소스→배지 색 매핑(§6-D)과 검색·필터 JS(§9)를 넣어줘. `_esc`/`_safe_url`은 절대 우회하지 말고, §8의 `scripts/rebuild_dashboard.py`도 만들어 7/8이 7/9와 같은 디자인으로 재생성되게 해줘. 원천 JSON이 없으면 `--style-only` 경로로라도 CSS는 통일되게 하고, `tests/test_step5_assemble.py`도 갱신해줘.
