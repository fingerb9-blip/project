"""Giscus(GitHub Discussions) 댓글 수 수집 — 인덱스 페이지 "💬 댓글 N개" 표시용.

data-mapping="pathname"으로 매핑되므로 각 날짜 페이지의 Discussion 제목은 giscus가
자동 생성한 pathname 문자열(예: "/2026-07-08.html")과 같다. GitHub GraphQL API로
저장소의 Discussion 목록을 순회해 제목 -> 댓글 수를 만들고, 날짜로 파싱되는 제목만
날짜별로 골라 저장한다. GITHUB_TOKEN(Actions가 자동 제공, discussions:read 권한만
필요)만 있으면 별도 유료 API 키 없이 동작한다.
"""

import json
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
_TIMEOUT = 15
_PAGE_SIZE = 50
_QUERY = """
query($owner: String!, $repo: String!, $after: String) {
  repository(owner: $owner, name: $repo) {
    discussions(first: %d, after: $after) {
      nodes {
        title
        comments { totalCount }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
""" % _PAGE_SIZE


def fetch_discussion_comment_counts(owner: str, repo: str, token: str) -> dict[str, int]:
    """저장소의 모든 Discussion 제목 -> 댓글 수(totalCount) 매핑을 가져온다 (페이지네이션 포함).

    Args:
        owner: 저장소 소유자 (예: "fingerb9-blip")
        repo: 저장소 이름 (예: "project")
        token: GitHub API 토큰 (discussions:read 권한 필요)

    Returns:
        {Discussion 제목: 댓글 수} dict

    Raises:
        RuntimeError: 요청 실패 또는 응답 형식이 예상과 다른 경우
    """
    headers = {"Authorization": f"bearer {token}"}
    counts: dict[str, int] = {}
    after = None

    while True:
        try:
            response = requests.post(
                _GRAPHQL_ENDPOINT,
                headers=headers,
                json={"query": _QUERY, "variables": {"owner": owner, "repo": repo, "after": after}},
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(str(payload["errors"]))
            discussions = payload["data"]["repository"]["discussions"]
        except (requests.exceptions.RequestException, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Discussions 댓글 수 조회 실패: {exc}") from exc

        for node in discussions["nodes"]:
            counts[node["title"]] = node["comments"]["totalCount"]

        if not discussions["pageInfo"]["hasNextPage"]:
            break
        after = discussions["pageInfo"]["endCursor"]

    return counts


def _pathname_to_date(pathname: str) -> str | None:
    """giscus pathname 매핑 Discussion 제목(예: "/2026-07-08.html")에서 날짜를 뽑는다.

    날짜 형식(YYYY-MM-DD)이 아닌 제목(예: index/archive/scraps 페이지, 또는 giscus와
    무관한 일반 토론)은 None을 반환해 걸러낸다.
    """
    stem = pathname.strip("/")
    if stem.endswith(".html"):
        stem = stem[: -len(".html")]
    parts = stem.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return stem
    return None


def run(output_path: str, owner: str, repo: str, token: str | None = None) -> dict[str, int]:
    """댓글 수를 가져와 날짜별로 정리해 저장한다.

    GITHUB_TOKEN이 없으면(로컬 실행 등) 조회 자체를 건너뛰고 기존 캐시를 그대로 반환한다.
    조회에 실패해도(네트워크 오류, 권한 부족 등) 이전 데이터를 유지한다 — 하루 사이에
    댓글 수 표시가 사라지는 "조용한 열화"를 막는다.

    Args:
        output_path: data/state/comment_counts.json 저장 경로
        owner, repo: GitHub 저장소
        token: GitHub API 토큰 (기본값: 환경변수 GITHUB_TOKEN)

    Returns:
        {날짜: 댓글 수} dict (저장된 최종 데이터)
    """
    output_path = Path(output_path)
    existing: dict[str, int] = {}
    if output_path.exists():
        with output_path.open(encoding="utf-8") as f:
            existing = json.load(f)

    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning("GITHUB_TOKEN 미설정, 댓글 수 갱신을 건너뜁니다")
        return existing

    try:
        title_counts = fetch_discussion_comment_counts(owner, repo, token)
    except RuntimeError as exc:
        logger.error("댓글 수 갱신 실패, 이전 데이터 유지: %s", exc)
        return existing

    by_date = dict(existing)
    for title, count in title_counts.items():
        date = _pathname_to_date(title)
        if date:
            by_date[date] = count

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(by_date, f, ensure_ascii=False, indent=2)

    return by_date
