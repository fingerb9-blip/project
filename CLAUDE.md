# 반도체 뉴스 데일리 브리핑 자동화 Agent

> 이 문서는 프로젝트의 **로드맵 개요**이자 Claude Code가 세션 시작 시 자동 로드하는 프로젝트 컨텍스트다.
> Phase별 상세 IPO 스펙(Input/Process/Output, 데이터 스키마)은 `docs/phaseN_ipo.md`로 분리하고 이 문서에서 참조한다.

## 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 목표 | 반도체 업계 뉴스를 매일 08:30에 자동 수집·선별·분류·요약해 GitHub Pages 대시보드로 발행 |
| 운영 두뇌 | Gemini API (무료 티어, Flash/Flash-Lite) — 중복 판정·분류·요약 |
| 개발 도구 | Claude Code (대화형) |
| 스케줄러 | 로컬 cron / 작업 스케줄러 (Phase 1) → GitHub Actions (Phase 2~) |
| 전달 채널 | GitHub Pages 대시보드 (브리핑 본문) + Gmail SMTP (앱 비밀번호, 실패 알림 전용) |
| 비용 원칙 | 유료 API 키 없이 무료 구성. Gemini 무료 티어 한도 근접 시에만 유료 전환 검토 |

## 설계 원칙

- **"AI는 초안, 사람은 판단."** 가치가 0인 ①수집·②스크리닝·⑤요약 초안을 AI에 넘기고, ③신뢰도 판단·④맥락화·해석은 사람이 유지
- **리스크 통제** (기획안 2-2):
  - 약신호 누락 방지 — "핵심/확인 필요/제외" 2단 분류, 애매하면 헤드라인 목록으로 포함
  - 요약 왜곡 방지 — 모든 요약에 원문 링크 + `[확정]`/`[관측]` 태그 필수
  - 침묵 실패 방지 — 파이프라인 실패 시 반드시 실패 알림 ("뉴스 없는 날"과 구분)
  - 조용한 품질 열화 방지 — 소스별 수집 건수 vs 최근 7일 평균 상시 노출, 0건 연속 시 경고

## 디렉토리 구조

```
├── config/            # 기업 별칭·카테고리·키워드·소스 등급 (YAML)
│   ├── company_aliases.yaml
│   ├── categories.yaml
│   ├── keywords.yaml
│   └── source_tiers.yaml
├── sources/           # feeds.yaml — RSS 피드 URL 목록
├── data/              # Step별 산출물 (raw → dedup → classified → summarized → archive)
├── logs/              # 실행 로그
├── src/               # step0~6 모듈, gemini_client, notify
├── docs/              # Phase별 상세 IPO 스펙 (아래 로드맵 참조)
├── main.py            # Step 0~6 순차 실행 진입점
└── CLAUDE.md          # (이 문서) 로드맵 개요 + 현재 진행 Phase
```

## 로드맵

**현재 진행: 🔨 Phase 1 (MVP)** — Step 0~6 핵심 경로를 로컬 수동 실행으로 완성 중

| Phase | 상태 | 목표 | 상세 스펙 |
|---|---|---|---|
| **Phase 1 — MVP** | 🔨 진행 중 | 수집 → 중복 제거 → 분류 → 요약 → 대시보드 발행. "브리핑 한 통을 실제로 받아보기" | `docs/phase1_ipo.md` |
| **Phase 2 — 자동화 & 커버리지 확장** | ⏳ 예정 | GitHub Actions 매일 자동 실행 + 상태 저장 + 실패 알림 / R&D·특허 소스 추가 / 피드백 루프 | `docs/phase2_ipo.md` |
| **Phase 3 — 이슈 추적 고도화** | ⏳ 예정 | 이상 신호 감지 & 대시보드 즉시 속보 / 이슈 지식그래프 기반 반복 이슈 경과 요약 | `docs/phase3_ipo.md` |
| **Phase 4 — 개인 애널리스트 확장** | 🔨 구현 완료 (PR 대기) | 경쟁 구도 레이더 | `docs/phase4_ipo.md` |

- Phase는 순차 진행하되, 각 Phase는 이전 Phase의 완성을 전제로 한다.
- Phase 4는 MVP(Phase 1~3) 안정화 이후 도입하는 차별화 확장으로, 코어 파이프라인 변경 없이 얹는다.

### Phase별 상세 스펙

> 현재 진행 중인 Phase 문서만 `@`로 자동 로드한다. Phase가 넘어가면 이전 Phase는 일반 링크로 되돌리고
> 새 Phase 문서를 `@`로 바꾼다 (컨텍스트 낭비 방지).

- Phase 1 — MVP 파이프라인: @docs/phase1_ipo.md (진행 중 — 자동 로드)
- Phase 2 — 자동화 & 커버리지 확장: docs/phase2_ipo.md
- Phase 3 — 이슈 추적 고도화: docs/phase3_ipo.md
- Phase 4 — 개인 애널리스트 확장: docs/phase4_ipo.md

## 작업 지침

- 지금은 **Phase 1**을 구현·테스트한다. 상세 IPO·Config 스키마·Gemini 연동·알림 규칙은 @docs/phase1_ipo.md를 따른다.
- 새 Phase에 착수할 때 이 문서 상단 "현재 진행" 표시와 로드맵 표의 상태(🔨/⏳/💡/✅)를 갱신한다.
- 각 `src/` 모듈은 독립 실행 가능하게 작성해 `main.py`에서 순차 호출하거나 Step별로 개별 테스트한다.
