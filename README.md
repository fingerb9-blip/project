# 반도체 뉴스 데일리 브리핑 자동화 Agent

반도체 업계 뉴스를 매일 자동 수집·선별·분류·요약해 이메일로 발송하는 파이프라인입니다.
전체 명세는 [CLAUDE.md](CLAUDE.md)를 참고하세요 (Step 0~6 IPO 정의, config 스키마, Gemini API 연동 스펙).

## 디렉토리 구조

```
├── config/            # 기업 별칭·카테고리·키워드·소스 등급 설정
├── sources/           # RSS 피드 목록
├── data/              # Step별 중간/최종 산출물 (raw -> dedup -> classified -> summarized -> archive)
├── logs/              # 실행 로그
├── src/               # Step0~6 모듈, gemini_client, notify
├── main.py            # Step 0~6 순차 실행 진입점
└── CLAUDE.md           # 파이프라인 기술 명세서
```

## 시작하기

```bash
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY, SMTP 계정 등 입력
python main.py
```

## 구현 상태

`src/` 각 모듈은 현재 함수 시그니처와 docstring만 정의된 스켈레톤 상태입니다.
`CLAUDE.md`의 Step별 Input/Process/Output 정의를 따라 `TODO` 부분을 순서대로 구현하세요.

| Step | 모듈 | 상태 |
|---|---|---|
| 0. 시작 | `src/step0_init.py` | 스켈레톤 |
| 1. 수집 | `src/step1_collect.py` | 스켈레톤 |
| 2. 중복 제거 | `src/step2_dedup.py` | 스켈레톤 |
| 3. 분류 | `src/step3_classify.py` | 스켈레톤 |
| 4. 요약 | `src/step4_summarize.py` | 스켈레톤 |
| 5. 조립 | `src/step5_assemble.py` | 스켈레톤 |
| 6. 발송·저장 | `src/step6_send.py` | 스켈레톤 |
