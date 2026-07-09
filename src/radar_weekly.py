"""Phase 4. 경쟁 구도 레이더 — 주간 기업별 언급량·톤·핵심 이슈 집계."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from src import gemini_client, issue_tracking

logger = logging.getLogger(__name__)


def load_tracked_companies(radar_companies_path) -> list[str]:
    """config/radar_companies.yaml을 읽어 집계 대상 기업 id 목록을 반환한다.

    Args:
        radar_companies_path: config/radar_companies.yaml 경로

    Returns:
        기업 id 목록 (config/company_aliases.yaml의 키와 일치)
    """
    with Path(radar_companies_path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("companies", [])


def week_label(today: str) -> str:
    """YYYY-MM-DD 날짜를 ISO 주차 표기(YYYY-Www)로 변환한다.

    Args:
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        "YYYY-Www" 형식 문자열 (예: "2026-W28")
    """
    iso_year, iso_week, _ = date.fromisoformat(today).isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def is_radar_day(weekday: int) -> bool:
    """주간 레이더를 갱신할 요일인지 판정한다 (월요일=0).

    호출부에서 KST 기준 요일을 넘겨야 한다 — 파이프라인의 today(UTC 라벨)와
    다른 값일 수 있으므로, 이 함수 자체는 순수하게 정수 요일만 받아 테스트하기 쉽게 한다.

    Args:
        weekday: datetime.weekday() 값 (월요일=0 ~ 일요일=6)

    Returns:
        월요일이면 True
    """
    return weekday == 0


_WINDOW_DAYS = 7


def load_week_dedup_articles(dedup_dir, today: str, days: int = _WINDOW_DAYS) -> list[dict]:
    """최근 days일치 data/dedup/YYYY-MM-DD.json을 모두 읽어 합친다.

    Args:
        dedup_dir: data/dedup 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열 (집계 기준일, 포함)
        days: 집계 기간(일)

    Returns:
        기간 내 존재하는 파일들의 기사 리스트를 합친 결과 (파일 없는 날은 건너뜀)
    """
    dedup_dir = Path(dedup_dir)
    articles: list[dict] = []
    for days_ago in range(days):
        day = (date.fromisoformat(today) - timedelta(days=days_ago)).isoformat()
        path = dedup_dir / f"{day}.json"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            articles.extend(json.load(f))
    return articles


def aggregate_mentions(articles: list[dict], tracked_companies: list[str]) -> dict[str, int]:
    """기업별 이번 주 언급 기사 수를 집계한다.

    Args:
        articles: load_week_dedup_articles 결과 (companies 필드 포함)
        tracked_companies: 집계 대상 기업 id 목록

    Returns:
        {회사id: 언급 기사 수} (모든 tracked_companies 키 포함, 언급 없으면 0)
    """
    counts = {company: 0 for company in tracked_companies}
    for article in articles:
        for company in article.get("companies") or []:
            if company in counts:
                counts[company] += 1
    return counts


def group_articles_by_company(articles: list[dict], tracked_companies: list[str]) -> dict[str, list[dict]]:
    """기업별로 해당 기업이 언급된 기사 리스트를 묶는다 (톤 판정 입력용).

    Args:
        articles: load_week_dedup_articles 결과
        tracked_companies: 집계 대상 기업 id 목록

    Returns:
        {회사id: 기사 리스트} (모든 tracked_companies 키 포함, 언급 없으면 빈 리스트)
    """
    grouped: dict[str, list[dict]] = {company: [] for company in tracked_companies}
    for article in articles:
        for company in article.get("companies") or []:
            if company in grouped:
                grouped[company].append(article)
    return grouped


_TONE_SNIPPET_LEN = 200

_TONE_SCHEMA = {
    "type": "object",
    "properties": {
        "tone": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "pos": {"type": "number"},
                    "neg": {"type": "number"},
                    "neu": {"type": "number"},
                },
                "required": ["company", "pos", "neg", "neu"],
            },
        }
    },
    "required": ["tone"],
}

_NEUTRAL_TONE = {"pos": 0.0, "neg": 0.0, "neu": 1.0}


def classify_tone(companies_articles: dict[str, list[dict]]) -> dict[str, dict]:
    """Gemini API(Flash-Lite)로 기업별 이번 주 기사 논조(긍정/부정/중립) 비율을 판정한다.

    언급이 없는 기업은 Gemini 호출 대상에서 제외하고 중립(neu=1.0)으로 채운다.
    호출 실패 시 모든 기업을 중립으로 대체한다.

    Args:
        companies_articles: {회사id: 해당 기업이 언급된 이번 주 기사 리스트}

    Returns:
        {회사id: {"pos": float, "neg": float, "neu": float}} (모든 companies_articles 키 포함)
    """
    mentioned = {company: arts for company, arts in companies_articles.items() if arts}
    tone = {company: dict(_NEUTRAL_TONE) for company in companies_articles if company not in mentioned}

    if not mentioned:
        return tone

    payload = {
        company: [
            {"title": a.get("title", ""), "snippet": a.get("raw_text", "")[:_TONE_SNIPPET_LEN]}
            for a in arts
        ]
        for company, arts in mentioned.items()
    }
    prompt = (
        "다음은 반도체 기업별로 이번 주 언급된 뉴스 기사 목록이다. "
        "각 기업에 대해 기사들의 전반적인 논조를 긍정(pos)/부정(neg)/중립(neu) 비율로 판정하라 "
        "(세 값의 합은 1.0). company 필드에는 입력에 사용된 키를 그대로 반환하라.\n\n"
        f"기업별 기사 목록: {json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        result = gemini_client.call_gemini(prompt, _TONE_SCHEMA, model=gemini_client.LITE_MODEL)
        by_company = {t["company"]: t for t in result.get("tone", [])}
    except RuntimeError as exc:
        logger.error("톤 판정 실패, 전체 중립으로 대체: %s", exc)
        by_company = {}

    for company in mentioned:
        matched = by_company.get(company)
        tone[company] = (
            {"pos": matched["pos"], "neg": matched["neg"], "neu": matched["neu"]}
            if matched
            else dict(_NEUTRAL_TONE)
        )

    return tone


_COMMENTARY_SCHEMA = {
    "type": "object",
    "properties": {"commentary": {"type": "string"}},
    "required": ["commentary"],
}


def generate_commentary(mentions: dict[str, int], top_issues: list[str], aliases_config: dict) -> str:
    """Gemini API(Flash)로 '이번 주 이슈의 중심' 한 문단 해설을 생성한다.

    실패 시 최다 언급 기업명을 이용한 간단한 템플릿 문장으로 대체한다.

    Args:
        mentions: aggregate_mentions 결과 ({회사id: 언급 수})
        top_issues: pick_top_issues 결과
        aliases_config: config/company_aliases.yaml 로드 결과 (기업 표기명 변환용)

    Returns:
        한 문단 해설 텍스트
    """
    display_mentions = {
        issue_tracking.entity_display_name(company, aliases_config): count
        for company, count in mentions.items()
    }
    prompt = (
        "다음은 이번 주 반도체 업계 기업별 언급 횟수와 최다 언급 이슈 목록이다. "
        "이번 주 업계 이슈의 중심이 무엇인지 한 문단으로 해설하라.\n\n"
        f"기업별 언급 횟수: {json.dumps(display_mentions, ensure_ascii=False)}\n"
        f"최다 언급 이슈: {json.dumps(top_issues, ensure_ascii=False)}"
    )
    try:
        result = gemini_client.call_gemini(prompt, _COMMENTARY_SCHEMA, model=gemini_client.DEFAULT_MODEL)
        return result["commentary"]
    except RuntimeError as exc:
        logger.error("주간 해설 생성 실패, 템플릿 문장으로 대체: %s", exc)
        if not display_mentions or max(display_mentions.values(), default=0) == 0:
            return "이번 주는 뚜렷한 언급 집중 없이 조용히 지나갔습니다."
        top_company = max(display_mentions, key=display_mentions.get)
        return f"이번 주는 {top_company} 관련 뉴스가 가장 많이 언급됐습니다."


_TOP_ISSUES_LIMIT = 3


def pick_top_issues(issues: list[dict], today: str, limit: int = _TOP_ISSUES_LIMIT) -> list[str]:
    """최근 WINDOW_DAYS일 내 갱신된 이슈 중 관련 기사 수가 많은 상위 N건을 고른다.

    Phase 3(이슈 지식그래프)가 이미 유지하는 data/state/issues.json을 그대로 재사용해,
    별도 Gemini 클러스터링 없이 "이번 주 최다 언급 이슈"를 뽑는다. last_updated가 없거나
    비어 있는 이슈는 (오래된 것으로 오판되지 않도록 fail-open이 아니라) 안전하게 제외한다.

    Args:
        issues: data/state/issues.json 로드 결과 (진행중/종료 모두 포함)
        today: YYYY-MM-DD 형식 날짜 문자열 (집계 기준일)
        limit: 상위 몇 건을 고를지

    Returns:
        "[기업] 제목" 형식의 이슈 헤드라인 문자열 리스트(관련 기사 수 내림차순)
    """
    cutoff = date.fromisoformat(today) - timedelta(days=_WINDOW_DAYS - 1)
    recent = []
    for issue in issues:
        last_updated = issue.get("last_updated")
        if not last_updated:
            continue
        if date.fromisoformat(last_updated) >= cutoff:
            recent.append(issue)
    ranked = sorted(recent, key=lambda i: len(i.get("related_article_ids") or []), reverse=True)
    top = ranked[:limit]
    return [f"[{issue.get('entity', '')}] {issue.get('title', '')}" for issue in top]


def run(
    dedup_dir: str,
    issues_path: str,
    aliases_config: dict,
    tracked_companies: list[str],
    today: str,
    output_dir: str,
) -> dict:
    """Phase 4 경쟁 구도 레이더 진입점. 매주 월요일 main.py에서 호출된다.

    Args:
        dedup_dir: data/dedup 디렉토리 경로
        issues_path: data/state/issues.json 경로
        aliases_config: config/company_aliases.yaml 로드 결과
        tracked_companies: 집계 대상 기업 id 목록
        today: YYYY-MM-DD 형식 날짜 문자열 (집계 기준일)
        output_dir: data/radar 디렉토리 경로

    Returns:
        생성된 주간 레이더 데이터 dict (data/radar/weekly-YYYY-Www.json에도 저장)
    """
    articles = load_week_dedup_articles(Path(dedup_dir), today)
    mentions = aggregate_mentions(articles, tracked_companies)
    grouped = group_articles_by_company(articles, tracked_companies)
    tone = classify_tone(grouped)

    issues = issue_tracking.load_issues(Path(issues_path))
    top_issues = pick_top_issues(issues, today)

    commentary = generate_commentary(mentions, top_issues, aliases_config)

    display_mentions = {
        issue_tracking.entity_display_name(company, aliases_config): count
        for company, count in mentions.items()
    }
    display_tone = {
        issue_tracking.entity_display_name(company, aliases_config): t for company, t in tone.items()
    }

    data = {
        "week": week_label(today),
        "mentions": display_mentions,
        "tone": display_tone,
        "top_issues": top_issues,
        "commentary": commentary,
    }

    output_path = Path(output_dir) / f"weekly-{data['week']}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data
