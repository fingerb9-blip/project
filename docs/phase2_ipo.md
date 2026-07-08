# Phase 2 — 자동화 & 커버리지 확장 IPO 명세

> **목표**: Phase 1 MVP를 매일 무인(無人) 실행되도록 자동화하고, 수집 소스를 딥테크 영역으로 넓히며,
> 사용자 피드백으로 필터가 스스로 개선되게 한다.
> **전제**: Phase 1(Step 0~6) 완성 및 로컬 수동 실행 검증 완료. 공통 기반(Config/Gemini/알림)은 @docs/phase1_ipo.md 참조.
>
> 기획안 근거: 2-4 Phase 2 + 2-5(R&D/특허 소스) + 2-6(피드백 루프).

## 2-A. GitHub Actions 자동 실행 (기획안 2-4 Phase 2)

- **Input**: 저장소 코드, GitHub Secrets(`GEMINI_API_KEY`, SMTP 앱 비밀번호, 네이버 API 키)
- **Process**:
  1. `.github/workflows/daily-briefing.yml` — cron `0 23 * * *` (UTC = KST 08:00) 스케줄 트리거 + `workflow_dispatch` 수동 실행
  2. Python 환경 구성 → 의존성 설치 → `python main.py` 실행
  3. 산출물(`data/`, `logs/`)을 저장소에 커밋 또는 Actions 아티팩트로 저장해 상태 영속화
  4. 워크플로우 실패/타임아웃 시 실패 알림 이메일 발송 — "침묵 실패" 방지
- **Output**: 매일 08:30 자동 발송된 브리핑 + 커밋된 날짜별 아카이브
- **상태 저장**: `data/*/YYYY-MM-DD.json`, `logs/`를 커밋(또는 artifact)해 기수집 기사 ID 중복 방지 상태 유지
- **실패 처리**: job 실패 시 `notify.py` 경유 알림. 로컬 cron과 달리 세션 토큰 만료·재인증 이슈 없음 (Gemini 키는 Secrets 상주 — 기획안 3장 근거)

```yaml
# .github/workflows/daily-briefing.yml (요지)
on:
  schedule: [{ cron: "0 23 * * *" }]   # KST 08:00
  workflow_dispatch:
jobs:
  briefing:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          SMTP_PASSWORD:  ${{ secrets.SMTP_PASSWORD }}
      - name: 상태 커밋
        run: git add data logs && git commit -m "brief: $(date +%F)" && git push
```

## 2-B. R&D/학술·특허 소스 추가 (기획안 2-5)

- **Input**: 반도체 학회(IEDM/ISSCC/VLSI 등) 프로그램 RSS·공식 페이지, 특허 공개 검색 API(KIPRIS, USPTO)
- **Process**:
  1. Step 1 수집 로직에 신규 소스 어댑터 추가 — RSS는 기존 `feedparser` 재사용, 특허 API는 전용 클라이언트
  2. 수집 항목을 기존 메타데이터 스키마로 정규화하고 `source_type` 필드로 구분
  3. Step 3 카테고리 태깅(장비·소재/팹리스·설계)에 그대로 연결 — 별도 파이프라인 신설 없음
- **Output**: `data/raw/YYYY-MM-DD.json`에 학술·특허 항목 포함 (기존 구조에 통합)
- **효과**: 차세대 소자 물성·패키징·설계 IP 연구 트렌드 조기 포착으로 기술적 맥락 심화

```yaml
# sources/feeds.yaml 확장 스키마
news:
  - { name: "디일렉", url: "https://...", tier: 2 }
academic:
  - { name: "IEDM", url: "https://.../program.rss", tier: 1 }
patent:
  - { name: "KIPRIS", api: "kipris", query: "반도체", tier: 1 }
```

```json
// data/raw 항목 확장 (source_type 추가)
{ "id": "...", "title": "...", "url": "...", "source": "IEDM",
  "source_type": "news|academic|patent", "published_at": "ISO8601", "raw_text": "..." }
```

## 2-C. 인간 피드백 기반 필터 자동화 / Human-in-the-loop (기획안 2-6)

- **Input**: 브리핑 이메일의 피드백 액션(노이즈 신고/키워드 제외 링크), `config/keywords.yaml`
- **Process**:
  1. Step 5 브리핑 조립 시 기사별 "노이즈 신고" 링크 삽입 — 기사 `id`·키워드를 인코딩한 `mailto:` 또는 폼 엔드포인트
  2. 피드백 수신 채널에서 신고된 기사/키워드를 파싱
  3. `keywords.yaml` 블랙리스트를 자동 업데이트(커밋/PR) — 사람 주 1회 검토와 결합
- **Output**: 갱신된 `keywords.yaml` — 운영될수록 사용자 취향에 맞게 필터가 정교화
- **리스크 통제**: 자동 반영 폭주 방지를 위해 임계(동일 키워드 N회 신고) + 사람 승인 게이트 적용.
  기획안 2-2 "도메인 감각 퇴화" 대응(주 1회 표본 검토)과 상호 보완 — 자동 피드백과 사람 검토가 필터 품질을 지속 개선

```json
// data/feedback/noise_reports.json (누적)
[ { "article_id": "sha1(url)", "keyword": "테마주", "reported_at": "ISO8601", "count": 3 } ]
```
