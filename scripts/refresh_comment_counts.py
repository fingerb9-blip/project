"""GitHub Discussions(Giscus) 댓글 수를 갱신하고 index.html에 반영한다.

data-mapping="pathname"으로 매핑된 각 날짜 페이지의 Discussion 제목에서 댓글 수를
가져와 data/state/comment_counts.json에 캐싱하고, index.html의 리포트 카드에
"💬 댓글 N개"로 반영한다. GITHUB_TOKEN(GitHub Actions가 자동 제공, discussions:read
권한만 필요)이 없으면 조회를 건너뛰고 기존 캐시를 유지한다 — 로컬에서 그냥 실행해도
안전하다.

Usage:
    python scripts/refresh_comment_counts.py
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import rebuild_dashboard  # noqa: E402
from src import giscus_comments, step5_assemble  # noqa: E402


def main() -> None:
    giscus_config = step5_assemble.load_giscus_config(BASE_DIR / "config" / "giscus.yaml")
    repo = giscus_config.get("repo", "")
    if "/" not in repo:
        print("[WARN] config/giscus.yaml의 repo 값이 없어 댓글 수 갱신을 건너뜁니다")
        return
    owner, name = repo.split("/", 1)

    output_path = BASE_DIR / "data" / "state" / "comment_counts.json"
    counts = giscus_comments.run(str(output_path), owner, name, token=os.environ.get("GITHUB_TOKEN"))
    print(f"[OK] 댓글 수 갱신: {len(counts)}개 날짜")

    rebuild_dashboard.rebuild_style_and_index(BASE_DIR)
    print("[OK] index.html 갱신 완료")


if __name__ == "__main__":
    main()
