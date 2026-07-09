# Dedup Cross-Tier 병합 안전망 + 관련도 스코어링 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) `step2_dedup.py`가 Gemini 클러스터링만으로 놓친 "원출처 vs 재인용" 중복(예: 갤럭시 언팩 삼성전자 뉴스룸 vs 디일렉)을 tier+기업+제목 토큰 유사도 기반 규칙으로 추가 병합하고, (2) `step3_classify.py`가 반도체 핵심 키워드 관련도 스코어를 계산해 본문 후반부에 스치듯 언급된 정치/경제 기사를 "제외" tier로 강제 이동시킨다.

**Architecture:** 두 기능 모두 "Gemini 판단 + 결정론적 규칙 기반 후처리 안전망"의 2단 구조를 따른다. Gemini 호출은 그대로 두고, 그 결과를 결정론적 규칙(tier 랭크, 기업 겹침, 키워드 위치·빈도)으로 보정한다 — Gemini가 놓치거나 과대포함해도 규칙이 마지막에 교정한다.

**Tech Stack:** Python 3.10+, pytest, `unittest.mock.patch` (기존 테스트 패턴과 동일)

## Global Constraints

- `src/step2_dedup.py`, `src/step3_classify.py`의 기존 public 함수 시그니처는 `run()`에서 호출하는 방식과 호환되어야 한다 (`main.py`는 수정하지 않음).
- Gemini API를 실제로 호출하는 테스트는 작성하지 않는다 — 기존 패턴대로 `@patch("src.stepN_xxx.gemini_client.call_gemini")`로 모킹한다.
- 새 로직은 기존 `config/*.yaml` 스키마를 깨지 않는 범위에서 추가한다 (기존 키 삭제/이름 변경 금지).
- 테스트는 `python -m pytest tests/test_step2_dedup.py tests/test_step3_classify.py -v` 로 실행한다 (프로젝트 루트에서).

---

## Task 1: `step2_dedup.py` — tier 활용 cross-tier 중복 병합 안전망

**배경 (현재 로직):**
- `group_by_title_similarity` (L55-80): 제목 전체 문자열의 `difflib.SequenceMatcher` 유사도가 0.9 이상이어야 그룹으로 묶는다. 삼성전자 뉴스룸과 디일렉처럼 같은 사건이라도 표현이 다르면 이 임계값을 넘지 못해 서로 다른 그룹(대표 기사)이 된다.
- `cluster_same_event` (L83-133): 그룹 대표만 Gemini(Flash-Lite)에 보내 "같은 사건이면 묶어라"라고만 지시한다. 이때 프롬프트에는 `title`+`snippet`만 들어가고, **tier(원출처/전문지/재인용) 정보나 기업 정보는 전달되지 않는다.** Gemini가 문맥만으로 동일 사건임을 못 잡아내면(실제 발생한 버그) 그대로 별도 클러스터로 남는다.
- `pick_representative` (L136-156): 이미 같은 `cluster_id`를 가진 기사들 중에서는 tier1을 우선 선택하지만, **애초에 cluster_id가 같아지지 않으면 이 로직에 도달하지 못한다.**

**개선 방향:** (a) Gemini 프롬프트/페이로드에 tier·기업 정보를 추가해 원출처-재인용 관계를 명시적으로 힌트로 주고, (b) Gemini 클러스터링 결과와 무관하게 동작하는 결정론적 후처리 `merge_cross_tier_duplicates`를 추가해 "기업 겹침 + tier 랭크 다름 + 제목 토큰 Jaccard 유사도 임계값 이상"인 클러스터를 강제 병합한다. (b)가 이번 버그(Gemini가 못 묶은 경우)에 대한 실질적 안전망이다.

**Files:**
- Modify: `src/step2_dedup.py`
- Test: `tests/test_step2_dedup.py`

**Interfaces:**
- Produces: `step2_dedup._tier_rank(source: str, source_tiers_config: dict) -> int`, `step2_dedup._tier_label(source: str, source_tiers_config: dict) -> str`, `step2_dedup._token_jaccard(title_a: str, title_b: str) -> float`, `step2_dedup.merge_cross_tier_duplicates(articles: list[dict], source_tiers_config: dict) -> list[dict]` (기존 필드 `companies`, `cluster_id`, `source`, `title`을 소비)
- Consumes (기존): `normalize_company_names`가 채운 `article["companies"]`, `cluster_same_event`가 채운 `article["cluster_id"]`

- [ ] **Step 1: `pick_representative`의 내부 `tier_rank`를 모듈 레벨 `_tier_rank`로 리팩터링 — 실패하는 테스트부터**

`tests/test_step2_dedup.py`에 추가 (파일 하단, 기존 `test_pick_representative_prefers_tier1_source` 아래):

```python
def test_tier_rank_orders_tier1_before_tier2_before_tier3_before_unknown():
    assert step2_dedup._tier_rank("삼성전자 뉴스룸", _SOURCE_TIERS) == 0
    assert step2_dedup._tier_rank("디일렉", _SOURCE_TIERS) == 1
    assert step2_dedup._tier_rank("네이버뉴스 재배포", _SOURCE_TIERS) == 2
    assert step2_dedup._tier_rank("알수없는소스", _SOURCE_TIERS) == 3
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step2_dedup.py::test_tier_rank_orders_tier1_before_tier2_before_tier3_before_unknown -v`
Expected: FAIL — `module 'src.step2_dedup' has no attribute '_tier_rank'`

- [ ] **Step 3: `_tier_rank`/`_tier_label` 구현 + `pick_representative` 리팩터링**

`src/step2_dedup.py`의 `pick_representative` 함수(L136-156)를 다음으로 교체:

```python
def _tier_rank(source: str, source_tiers_config: dict) -> int:
    if source in source_tiers_config.get("tier1_원출처", []):
        return 0
    if source in source_tiers_config.get("tier2_전문지", []):
        return 1
    if source in source_tiers_config.get("tier3_재인용", []):
        return 2
    return 3


def _tier_label(source: str, source_tiers_config: dict) -> str:
    labels = {0: "원출처", 1: "전문지", 2: "재인용", 3: "미분류"}
    return labels[_tier_rank(source, source_tiers_config)]


def pick_representative(cluster_articles: list[dict], source_tiers_config: dict) -> dict:
    """클러스터 내에서 source_tiers.yaml 1차(원출처) 우선으로 대표 기사를 선정한다.

    Args:
        cluster_articles: 동일 cluster_id를 가진 기사 리스트
        source_tiers_config: config/source_tiers.yaml 로드 결과

    Returns:
        대표 기사 dict
    """
    return min(
        cluster_articles,
        key=lambda a: _tier_rank(a["source"], source_tiers_config),
    )
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step2_dedup.py -v`
Expected: 기존 테스트 전부 PASS + 신규 `_tier_rank` 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/step2_dedup.py tests/test_step2_dedup.py
git commit -m "refactor: extract _tier_rank helper from pick_representative"
```

---

- [ ] **Step 6: `cluster_same_event`에 tier/기업 정보 전달 — 실패하는 테스트부터**

`cluster_same_event`의 시그니처가 `source_tiers_config`를 받도록 바뀌므로, 기존 테스트 4개를 업데이트한다. `tests/test_step2_dedup.py`에서 아래 4개 테스트를 교체:

```python
@patch("src.step2_dedup.gemini_client.call_gemini")
def test_cluster_same_event_sends_one_representative_per_title_group(mock_call):
    mock_call.return_value = {"clusters": [["a1"]]}
    articles = [
        _article(id="a1", url="https://a.com/1"),
        _article(id="a2", url="https://b.com/1"),  # 동일 제목, 다른 URL (재배포)
        _article(id="a3", title="SK하이닉스, 청주 공장 증설 착공", url="https://c.com/1"),
    ]

    step2_dedup.cluster_same_event(articles, _SOURCE_TIERS)

    prompt = mock_call.call_args[0][0]
    assert '"a1"' in prompt
    assert '"a3"' in prompt
    assert '"a2"' not in prompt  # a2는 a1과 같은 그룹이라 대표(a1)로만 전달됨


@patch("src.step2_dedup.gemini_client.call_gemini")
def test_cluster_same_event_includes_tier_and_company_hints_in_prompt(mock_call):
    mock_call.return_value = {"clusters": [["a1"]]}
    articles = step2_dedup.normalize_company_names(
        [_article(id="a1", source="삼성전자 뉴스룸")], _ALIASES
    )

    step2_dedup.cluster_same_event(articles, _SOURCE_TIERS)

    prompt = mock_call.call_args[0][0]
    assert "원출처" in prompt
    assert "samsung_electronics" in prompt


@patch("src.step2_dedup.gemini_client.call_gemini")
def test_cluster_same_event_assigns_same_cluster_id_within_title_group(mock_call):
    mock_call.return_value = {"clusters": [["a1"]]}
    articles = [
        _article(id="a1", url="https://a.com/1"),
        _article(id="a2", url="https://b.com/1"),
    ]

    result = step2_dedup.cluster_same_event(articles, _SOURCE_TIERS)

    by_id = {a["id"]: a for a in result}
    assert by_id["a1"]["cluster_id"] == by_id["a2"]["cluster_id"]


@patch("src.step2_dedup.gemini_client.call_gemini", side_effect=RuntimeError("boom"))
def test_cluster_same_event_keeps_title_group_merged_when_gemini_fails(mock_call):
    articles = [
        _article(id="a1", url="https://a.com/1"),
        _article(id="a2", url="https://b.com/1"),
        _article(id="a3", title="SK하이닉스, 청주 공장 증설 착공", url="https://c.com/1"),
    ]

    result = step2_dedup.cluster_same_event(articles, _SOURCE_TIERS)

    by_id = {a["id"]: a for a in result}
    assert by_id["a1"]["cluster_id"] == by_id["a2"]["cluster_id"]
    assert by_id["a1"]["cluster_id"] != by_id["a3"]["cluster_id"]


def test_cluster_same_event_handles_empty_list():
    assert step2_dedup.cluster_same_event([], _SOURCE_TIERS) == []
```

- [ ] **Step 7: 테스트 실행 → 신규/변경 테스트 실패 확인**

Run: `python -m pytest tests/test_step2_dedup.py -v`
Expected: `test_cluster_same_event_includes_tier_and_company_hints_in_prompt` FAIL (아직 프롬프트에 tier/기업 정보 없음), 나머지는 `cluster_same_event()` 인자 개수 불일치로 TypeError FAIL

- [ ] **Step 8: `cluster_same_event` 구현 — 페이로드/프롬프트에 tier·기업 정보 추가**

`src/step2_dedup.py`의 `cluster_same_event` 함수(L83-133)를 다음으로 교체 (시그니처와 payload/prompt만 변경, 클러스터링 결과 처리 로직은 동일):

```python
def cluster_same_event(articles: list[dict], source_tiers_config: dict) -> list[dict]:
    """제목 유사도로 사전 그룹핑한 뒤, 그룹 대표만 Gemini API(Flash-Lite)에 배치로 전달해
    동일 사건을 클러스터링한다.

    Args:
        articles: 기업명 정규화된 기사 리스트
        source_tiers_config: config/source_tiers.yaml 로드 결과 (프롬프트 힌트에 사용)

    Returns:
        cluster_id가 부여된 기사 리스트
    """
    if not articles:
        return articles

    groups = group_by_title_similarity(articles)
    representatives = [group[0] for group in groups]

    payload = [
        {
            "id": a["id"],
            "title": a["title"],
            "snippet": a.get("raw_text", "")[:_SNIPPET_LEN],
            "companies": a.get("companies", []),
            "source_tier": _tier_label(a["source"], source_tiers_config),
        }
        for a in representatives
    ]
    prompt = (
        "다음은 오늘 수집된 반도체 업계 뉴스 기사 목록이다. "
        "같은 사건(동일 발표·계약·인사 등)을 다루는 기사끼리 id를 묶어 clusters 배열로 반환하라. "
        "companies가 겹치고 source_tier가 다른 두 기사(예: 원출처의 공식 발표와 "
        "전문지·재인용 매체의 후속 보도)는 표현이 달라도 같은 사건이면 반드시 같은 클러스터로 묶어라. "
        "서로 다른 사건이면 별도 클러스터로 둔다.\n\n"
        f"기사 목록: {json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        result = gemini_client.call_gemini(prompt, _CLUSTER_SCHEMA, model=gemini_client.LITE_MODEL)
        clusters = result.get("clusters", [])
    except RuntimeError as exc:
        logger.error("클러스터링 실패, 제목 유사도 그룹 단위로 대체: %s", exc)
        clusters = []

    rep_id_to_cluster: dict[str, str] = {}
    for member_ids in clusters:
        if not member_ids:
            continue
        cluster_id = hashlib.sha1("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()[:12]
        for member_id in member_ids:
            rep_id_to_cluster[member_id] = cluster_id

    for group in groups:
        rep_id = group[0]["id"]
        if rep_id not in rep_id_to_cluster:
            rep_id_to_cluster[rep_id] = hashlib.sha1(rep_id.encode("utf-8")).hexdigest()[:12]
        cluster_id = rep_id_to_cluster[rep_id]
        for article in group:
            article["cluster_id"] = cluster_id

    return articles
```

- [ ] **Step 9: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step2_dedup.py -v`
Expected: 전부 PASS

- [ ] **Step 10: 커밋**

```bash
git add src/step2_dedup.py tests/test_step2_dedup.py
git commit -m "feat: pass tier/company hints to gemini clustering prompt"
```

---

- [ ] **Step 11: `merge_cross_tier_duplicates` 안전망 — 실패하는 테스트부터 (갤럭시 언팩 재현 사례)**

`tests/test_step2_dedup.py` 파일 끝에 추가:

```python
def test_token_jaccard_high_for_overlapping_titles():
    similarity = step2_dedup._token_jaccard(
        "삼성전자 갤럭시 언팩 2026 개최, 엑시노스 2600 공식 발표",
        "갤럭시 언팩 2026 현장, 삼성전자 엑시노스 2600 탑재 공식화",
    )
    assert similarity >= 0.4


def test_token_jaccard_ignores_trailing_punctuation():
    similarity = step2_dedup._token_jaccard(
        "삼성전자, 갤럭시 언팩 2026 개최",
        "갤럭시 언팩 2026 삼성전자 참가",
    )
    assert similarity >= 0.5  # 쉼표 등 꼬리 문장부호 때문에 "삼성전자,"≠"삼성전자"로 갈라지면 안 됨


def test_token_jaccard_low_for_unrelated_titles():
    similarity = step2_dedup._token_jaccard(
        "삼성전자, 갤럭시 언팩 2026에서 갤럭시 S26 공식 발표",
        "SK하이닉스, 청주 공장 증설 착공",
    )
    assert similarity < 0.3


def test_merge_cross_tier_duplicates_merges_newsroom_and_reprint_of_same_event():
    # 실제 버그 재현: Gemini 클러스터링이 삼성전자 뉴스룸(원출처)과
    # 디일렉(재인용) 갤럭시 언팩 기사를 서로 다른 클러스터로 남긴 경우
    newsroom = _article(
        id="a1",
        title="삼성전자 갤럭시 언팩 2026 개최, 엑시노스 2600 공식 발표",
        source="삼성전자 뉴스룸",
        cluster_id="cluster-newsroom",
    )
    reprint = _article(
        id="a2",
        title="갤럭시 언팩 2026 현장, 삼성전자 엑시노스 2600 탑재 공식화",
        source="디일렉",
        cluster_id="cluster-dielec",
    )
    articles = step2_dedup.normalize_company_names([newsroom, reprint], _ALIASES)

    result = step2_dedup.merge_cross_tier_duplicates(articles, _SOURCE_TIERS)

    by_id = {a["id"]: a for a in result}
    assert by_id["a1"]["cluster_id"] == by_id["a2"]["cluster_id"]


def test_merge_cross_tier_duplicates_keeps_different_companies_separate():
    samsung_article = _article(
        id="a1",
        title="삼성전자, HBM4 수율 개선 발표",
        source="삼성전자 뉴스룸",
        cluster_id="cluster-a",
    )
    hynix_article = _article(
        id="a2",
        title="SK하이닉스, HBM4 수율 개선 발표",
        source="네이버뉴스 재배포",
        cluster_id="cluster-b",
    )
    aliases = dict(_ALIASES, sk_hynix={"aliases": ["SK하이닉스"], "segment": ["메모리"]})
    articles = step2_dedup.normalize_company_names([samsung_article, hynix_article], aliases)

    result = step2_dedup.merge_cross_tier_duplicates(articles, _SOURCE_TIERS)

    by_id = {a["id"]: a for a in result}
    assert by_id["a1"]["cluster_id"] != by_id["a2"]["cluster_id"]


def test_merge_cross_tier_duplicates_keeps_same_tier_separate_events():
    # 같은 tier(둘 다 원출처)인 별개 발표는 기업이 겹쳐도 병합하지 않는다
    article_a = _article(
        id="a1",
        title="삼성전자, 갤럭시 언팩 2026에서 갤럭시 S26 공식 발표",
        source="삼성전자 뉴스룸",
        cluster_id="cluster-a",
    )
    article_b = _article(
        id="a2",
        title="삼성전자, HBM4 수율 개선 발표",
        source="삼성전자 뉴스룸",
        cluster_id="cluster-b",
    )
    articles = step2_dedup.normalize_company_names([article_a, article_b], _ALIASES)

    result = step2_dedup.merge_cross_tier_duplicates(articles, _SOURCE_TIERS)

    by_id = {a["id"]: a for a in result}
    assert by_id["a1"]["cluster_id"] != by_id["a2"]["cluster_id"]
```

- [ ] **Step 12: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step2_dedup.py -v`
Expected: 위 5개 신규 테스트가 `AttributeError: module 'src.step2_dedup' has no attribute '_token_jaccard'` 등으로 FAIL

- [ ] **Step 13: `_token_jaccard`, `_is_cross_tier_duplicate`, `merge_cross_tier_duplicates` 구현**

`src/step2_dedup.py`의 상단 상수 블록(L27-28)에 추가:

```python
_SNIPPET_LEN = 300
_TITLE_SIMILARITY_THRESHOLD = 0.9
_TOKEN_JACCARD_THRESHOLD = 0.3
_MIN_TOKEN_LEN = 2
_TOKEN_STRIP_CHARS = ",.\"'…·"
```

`pick_representative` 함수(Task 1 Step 3에서 재정의한 위치) 바로 뒤에 추가:

```python
def _title_tokens(title: str) -> set[str]:
    tokens = set()
    for raw in title.split():
        token = raw.strip(_TOKEN_STRIP_CHARS)
        if len(token) >= _MIN_TOKEN_LEN:
            tokens.add(token)
    return tokens


def _token_jaccard(title_a: str, title_b: str) -> float:
    tokens_a, tokens_b = _title_tokens(title_a), _title_tokens(title_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _is_cross_tier_duplicate(
    article_a: dict, article_b: dict, source_tiers_config: dict
) -> bool:
    """Gemini 클러스터링이 놓친 원출처/재인용 중복을 잡는 보조 판정.

    기업이 겹치고, tier가 서로 다르고(같은 발표를 다른 등급 소스가 다뤘다는 신호),
    제목 토큰 유사도가 임계값 이상이면 동일 사건으로 간주한다.
    """
    shared_companies = set(article_a.get("companies", [])) & set(article_b.get("companies", []))
    if not shared_companies:
        return False
    rank_a = _tier_rank(article_a["source"], source_tiers_config)
    rank_b = _tier_rank(article_b["source"], source_tiers_config)
    if rank_a == rank_b:
        return False
    return _token_jaccard(article_a["title"], article_b["title"]) >= _TOKEN_JACCARD_THRESHOLD


def merge_cross_tier_duplicates(articles: list[dict], source_tiers_config: dict) -> list[dict]:
    """cluster_same_event 결과에 원출처/재인용 중복 병합 안전망을 적용한다.

    Gemini 클러스터링이 표현 차이 때문에 놓친 동일 사건 쌍을, 기업 겹침 + tier 차이 +
    제목 토큰 유사도 규칙으로 강제 병합한다 (Gemini 성공/실패 여부와 무관하게 동작).

    Args:
        articles: cluster_id가 부여된 기사 리스트
        source_tiers_config: config/source_tiers.yaml 로드 결과

    Returns:
        병합된 cluster_id가 적용된 기사 리스트
    """
    clusters: dict[str, list[dict]] = {}
    for article in articles:
        clusters.setdefault(article["cluster_id"], []).append(article)

    parent = {cluster_id: cluster_id for cluster_id in clusters}

    def find(cluster_id: str) -> str:
        while parent[cluster_id] != cluster_id:
            cluster_id = parent[cluster_id]
        return cluster_id

    def union(cluster_id_a: str, cluster_id_b: str) -> None:
        root_a, root_b = find(cluster_id_a), find(cluster_id_b)
        if root_a != root_b:
            parent[root_b] = root_a

    cluster_ids = list(clusters.keys())
    for i, cluster_id_a in enumerate(cluster_ids):
        for cluster_id_b in cluster_ids[i + 1 :]:
            if _is_cross_tier_duplicate(
                clusters[cluster_id_a][0], clusters[cluster_id_b][0], source_tiers_config
            ):
                union(cluster_id_a, cluster_id_b)

    for article in articles:
        article["cluster_id"] = find(article["cluster_id"])

    return articles
```

- [ ] **Step 14: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step2_dedup.py -v`
Expected: 전부 PASS

- [ ] **Step 15: `run()`에 병합 단계 연결**

`src/step2_dedup.py`의 `run()` 함수(L159-189) 중 본문 로직을 다음으로 교체 (docstring·저장 로직은 그대로 유지, 클러스터링 다음 줄만 추가):

```python
    articles = normalize_company_names(raw_articles, aliases_config)
    articles = cluster_same_event(articles, source_tiers_config)
    articles = merge_cross_tier_duplicates(articles, source_tiers_config)
```

- [ ] **Step 16: 전체 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step2_dedup.py -v`
Expected: 전부 PASS

- [ ] **Step 17: 커밋**

```bash
git add src/step2_dedup.py tests/test_step2_dedup.py
git commit -m "feat: add cross-tier duplicate merge safety net for gemini clustering misses"
```

---

## Task 2: `config/keywords.yaml` + `step3_classify.py` — 반도체 핵심 키워드 관련도 스코어링

**배경 (현재 로직):**
- `filter_by_keywords` (L39-63)는 `blacklist`(근거없는_시황: 급등/테마주/찌라시) 매칭 시에만 제외한다. "가계대출", "환율", "노조 파업" 등 반도체와 무관한 정치/경제 기사는 이 블랙리스트 단어를 쓰지 않으므로 통과한다.
- `classify_tier_and_category` (L66-114)는 Gemini의 tier 판단을 그대로 신뢰한다 (기업 미특정+규제 키워드일 때만 카테고리를 보정). 본문 후반부에 "반도체" 관련어가 스치듯 한 번 언급된 기사를 Gemini가 "확인 필요"로 잘못 분류해도 교정할 규칙이 없다.

**개선 방향:** `config/keywords.yaml`에 반도체 핵심 기술 키워드 화이트리스트 그룹(`반도체_핵심`)을 추가하고, 제목/본문 등장 위치·빈도 기반 관련도 스코어(`relevance_score`)를 계산한다. 제목에 등장하면 가중치 3, 본문에 여러 번 또는 전반부에 등장하면 2, 본문 후반부에 딱 1회만 등장하면 1을 부여한다. `classify_tier_and_category`에서 이 스코어가 1 이하이고 다른 화이트리스트 키워드 힌트도 없는 기사는 Gemini 판단과 무관하게 강제로 "제외" tier로 보낸다 — 단, 규제·공급망 등 기존 화이트리스트 그룹에 이미 매칭된 기사(예: 반도체법·수출통제 기사)는 핵심 키워드가 없어도 제외되지 않도록 보호한다.

**Files:**
- Modify: `config/keywords.yaml`
- Modify: `src/step3_classify.py`
- Test: `tests/test_step3_classify.py` (신규 생성)

**Interfaces:**
- Produces: `step3_classify.compute_relevance_score(article: dict, core_keywords: list[str]) -> int`, `article["relevance_score"]` 필드 (filter_by_keywords가 채움), `_CORE_KEYWORD_GROUP = "반도체_핵심"` 상수
- Consumes: `keywords_config["whitelist"]["반도체_핵심"]` (신규 config 그룹), 기존 `article["keyword_hints"]`

- [ ] **Step 1: `config/keywords.yaml`에 반도체_핵심 화이트리스트 그룹 추가**

`config/keywords.yaml`을 다음으로 교체:

```yaml
whitelist:
  공정_기술: ["EUV", "GAA", "수율", "패키징"]
  공급망: ["HBM", "웨이퍼", "파운드리 증설"]
  규제_무역: ["수출통제", "관세", "반도체법"]
  기업활동: ["M&A", "합작법인", "증설"]
  시장분석_투자의견: ["실적 전망", "투자의견"]   # 근거 있는 투자의견은 화이트리스트
  반도체_핵심: ["HBM", "파운드리", "D램", "낸드", "웨이퍼", "팹", "노광"]   # 관련도 스코어링 전용, keyword_hints에는 포함하지 않음
blacklist:
  근거없는_시황: ["급등", "테마주", "찌라시"]

# Phase 3 이상 신호 감지(step1_5_anomaly_detect.py)가 급증 여부를 판단할 때 사용하는
# 위험 키워드. 화이트리스트/블랙리스트와 별개로 매시 배치에서만 참조한다.
risk_keywords: ["규제", "화재", "셧다운", "리콜"]
```

- [ ] **Step 2: 테스트 파일 생성 + `compute_relevance_score` 실패하는 테스트부터**

`tests/test_step3_classify.py` 신규 생성:

```python
from unittest.mock import patch

from src import step3_classify

_KEYWORDS = {
    "whitelist": {
        "공급망": ["HBM", "웨이퍼", "파운드리 증설"],
        "규제_무역": ["수출통제", "관세", "반도체법"],
        "반도체_핵심": ["HBM", "파운드리", "D램", "낸드", "웨이퍼", "팹", "노광"],
    },
    "blacklist": {
        "근거없는_시황": ["급등", "테마주", "찌라시"],
    },
}

_CATEGORIES = {
    "메모리": {"segment": ["메모리", "HBM"]},
    "규제·정책": {"segment": []},
}

_CORE_KEYWORDS = _KEYWORDS["whitelist"]["반도체_핵심"]


def _article(**overrides):
    article = {
        "id": "a1",
        "title": "삼성전자, HBM4 수율 개선 발표",
        "url": "https://example.com/1",
        "source": "삼성전자 뉴스룸",
        "raw_text": "삼성전자가 HBM4 공정 수율을 개선했다.",
        "companies": ["samsung_electronics"],
    }
    article.update(overrides)
    return article


def test_compute_relevance_score_high_when_keyword_in_title():
    article = _article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")
    score = step3_classify.compute_relevance_score(article, _CORE_KEYWORDS)
    assert score >= 3


def test_compute_relevance_score_low_for_single_back_half_mention():
    body = "정부가 가계대출 관리 강화안을 발표하며 은행권 대출 문턱이 높아졌다. " * 10
    body += "업계에서는 반도체 업황 영향으로 파운드리 수요도 변수라는 말이 나온다."
    article = _article(
        id="a2",
        title="정부, 가계대출 관리 강화안 발표...은행권 대출 문턱 높아진다",
        raw_text=body,
        companies=[],
    )
    score = step3_classify.compute_relevance_score(article, _CORE_KEYWORDS)
    assert score <= 1


def test_compute_relevance_score_zero_when_no_core_keyword_mentioned():
    article = _article(
        id="a3",
        title="원/달러 환율, 노조 파업 여파로 급변동",
        raw_text="반도체 업종을 포함한 수출 기업들이 환율 영향을 우려하고 있다.",
        companies=[],
    )
    score = step3_classify.compute_relevance_score(article, _CORE_KEYWORDS)
    assert score == 0
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step3_classify.py -v`
Expected: 3개 모두 `AttributeError: module 'src.step3_classify' has no attribute 'compute_relevance_score'`로 FAIL

- [ ] **Step 4: `compute_relevance_score` 구현**

`src/step3_classify.py`의 상단 상수 블록(L30-32)을 다음으로 교체:

```python
_REGULATION_CATEGORY = "규제·정책"
_REGULATION_KEYWORD_GROUP = "규제_무역"
_CORE_KEYWORD_GROUP = "반도체_핵심"
_SNIPPET_LEN = 300
_TITLE_MATCH_WEIGHT = 3
_BODY_STRONG_WEIGHT = 2
_BODY_WEAK_WEIGHT = 1
_RELEVANCE_EXCLUDE_THRESHOLD = 1
```

`_matched_keywords` 함수(L35-36) 바로 뒤에 추가:

```python
def _find_all_occurrences(text: str, keyword: str) -> list[int]:
    positions = []
    start = 0
    while True:
        idx = text.find(keyword, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def compute_relevance_score(article: dict, core_keywords: list[str]) -> int:
    """제목/본문에서 반도체 핵심 키워드 등장 위치·빈도로 관련도 점수를 매긴다.

    제목에 등장하면 가중치를 높게, 본문 후반부에 1회만 등장하면 낮게 준다.

    Args:
        article: title, raw_text 필드를 포함한 기사 dict
        core_keywords: config/keywords.yaml의 whitelist.반도체_핵심 리스트

    Returns:
        관련도 점수 (높을수록 반도체 관련도가 높음)
    """
    title = article["title"]
    body = article.get("raw_text", "")
    midpoint = len(body) / 2
    score = 0
    for keyword in core_keywords:
        if keyword in title:
            score += _TITLE_MATCH_WEIGHT
            continue
        positions = _find_all_occurrences(body, keyword)
        if not positions:
            continue
        if len(positions) == 1 and positions[0] >= midpoint:
            score += _BODY_WEAK_WEIGHT
        else:
            score += _BODY_STRONG_WEIGHT
    return score
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step3_classify.py -v`
Expected: 3개 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add config/keywords.yaml src/step3_classify.py tests/test_step3_classify.py
git commit -m "feat: add core semiconductor keyword relevance scoring"
```

---

- [ ] **Step 7: `filter_by_keywords`가 relevance_score를 채우도록 — 실패하는 테스트부터**

`tests/test_step3_classify.py`에 추가:

```python
def test_filter_by_keywords_attaches_relevance_score():
    articles = [_article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")]
    result = step3_classify.filter_by_keywords(articles, _KEYWORDS)
    assert result[0]["relevance_score"] >= 3


def test_filter_by_keywords_excludes_blacklist_regardless_of_relevance_score():
    articles = [
        _article(
            id="a4",
            title="삼성전자 HBM 테마주 급등",
            raw_text="",
        )
    ]
    result = step3_classify.filter_by_keywords(articles, _KEYWORDS)
    assert result == []


def test_filter_by_keywords_keyword_hints_excludes_core_group():
    # 반도체_핵심은 relevance_score 산출 전용이며 keyword_hints에는 노출되지 않는다
    articles = [_article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")]
    result = step3_classify.filter_by_keywords(articles, _KEYWORDS)
    assert "반도체_핵심" not in result[0]["keyword_hints"]
    assert "공급망" in result[0]["keyword_hints"]
```

- [ ] **Step 8: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step3_classify.py -v`
Expected: `test_filter_by_keywords_attaches_relevance_score`, `test_filter_by_keywords_keyword_hints_excludes_core_group` FAIL (KeyError `relevance_score` / 반도체_핵심이 keyword_hints에 그대로 포함됨)

- [ ] **Step 9: `filter_by_keywords` 구현**

`src/step3_classify.py`의 `filter_by_keywords` 함수(L39-63)를 다음으로 교체:

```python
def filter_by_keywords(articles: list[dict], keywords_config: dict) -> list[dict]:
    """keywords.yaml 화이트리스트/블랙리스트로 1차 필터링하고 관련도 점수를 매긴다.

    블랙리스트 키워드가 매칭된 기사는 제외하고, 화이트리스트 매칭 그룹(반도체_핵심 제외)은
    keyword_hints 필드에 남겨 Gemini 분류의 참고 신호로 사용한다. 반도체_핵심 그룹은
    keyword_hints와 별개로 relevance_score 계산에만 사용한다.

    Args:
        articles: Step 2 결과 기사 리스트
        keywords_config: config/keywords.yaml 로드 결과

    Returns:
        블랙리스트 키워드가 제거된 기사 리스트
    """
    whitelist = keywords_config.get("whitelist", {})
    blacklist = keywords_config.get("blacklist", {})
    core_keywords = whitelist.get(_CORE_KEYWORD_GROUP, [])
    hint_whitelist = {k: v for k, v in whitelist.items() if k != _CORE_KEYWORD_GROUP}

    filtered = []
    for article in articles:
        text = f"{article['title']} {article.get('raw_text', '')}"
        if _matched_keywords(text, blacklist):
            continue
        article["keyword_hints"] = _matched_keywords(text, hint_whitelist)
        article["relevance_score"] = compute_relevance_score(article, core_keywords)
        filtered.append(article)

    return filtered
```

- [ ] **Step 10: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step3_classify.py -v`
Expected: 전부 PASS

- [ ] **Step 11: 커밋**

```bash
git add src/step3_classify.py tests/test_step3_classify.py
git commit -m "feat: attach relevance_score to articles in filter_by_keywords"
```

---

- [ ] **Step 12: `classify_tier_and_category`가 저관련도 기사를 강제 제외 — 실패하는 테스트부터 (실제 문제 기사 예시)**

`tests/test_step3_classify.py`에 추가:

```python
@patch("src.step3_classify.gemini_client.call_gemini")
def test_classify_forces_exclude_when_relevance_low_and_no_keyword_hints(mock_call):
    # 실제 버그 재현: 네이버뉴스 재배포 기사가 본문 후반부에 반도체를 스치듯
    # 언급했을 뿐인데 Gemini가 "확인 필요"로 분류한 경우
    mock_call.return_value = {
        "results": [{"id": "a3", "tier": "확인 필요", "category": []}]
    }
    article = _article(
        id="a3",
        title="원/달러 환율, 노조 파업 여파로 급변동",
        source="네이버뉴스 재배포",
        raw_text="반도체 업종을 포함한 수출 기업들이 환율 영향을 우려하고 있다.",
        companies=[],
    )
    articles = step3_classify.filter_by_keywords([article], _KEYWORDS)

    result = step3_classify.classify_tier_and_category(articles, _CATEGORIES)

    assert result[0]["tier"] == "제외"


@patch("src.step3_classify.gemini_client.call_gemini")
def test_classify_keeps_gemini_tier_when_relevance_high(mock_call):
    mock_call.return_value = {
        "results": [{"id": "a1", "tier": "핵심", "category": ["메모리"]}]
    }
    article = _article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")
    articles = step3_classify.filter_by_keywords([article], _KEYWORDS)

    result = step3_classify.classify_tier_and_category(articles, _CATEGORIES)

    assert result[0]["tier"] == "핵심"


@patch("src.step3_classify.gemini_client.call_gemini")
def test_classify_does_not_exclude_low_relevance_article_with_regulation_hint(mock_call):
    # 반도체_핵심 키워드는 없지만 규제_무역 화이트리스트에 매칭된 기사는 보호되어야 한다
    mock_call.return_value = {
        "results": [{"id": "a5", "tier": "확인 필요", "category": []}]
    }
    article = _article(
        id="a5",
        title="정부, 반도체법 개정안 발표...수출통제 강화",
        raw_text="",
        companies=[],
    )
    articles = step3_classify.filter_by_keywords([article], _KEYWORDS)

    result = step3_classify.classify_tier_and_category(articles, _CATEGORIES)

    assert result[0]["tier"] == "확인 필요"
```

- [ ] **Step 13: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step3_classify.py -v`
Expected: `test_classify_forces_exclude_when_relevance_low_and_no_keyword_hints` FAIL (tier가 "확인 필요"로 남음)

- [ ] **Step 14: `classify_tier_and_category` 구현**

`src/step3_classify.py`의 `classify_tier_and_category` 함수(L66-114) 중 for 루프 본문(L105-112)을 다음으로 교체:

```python
    for article in articles:
        result = by_id.get(article["id"], {"tier": "확인 필요", "category": []})
        article["tier"] = result["tier"]
        article["category"] = list(result["category"])
        no_company = not article.get("companies")
        has_regulation_hint = _REGULATION_KEYWORD_GROUP in article.get("keyword_hints", [])
        if no_company and has_regulation_hint and _REGULATION_CATEGORY not in article["category"]:
            article["category"].append(_REGULATION_CATEGORY)

        low_relevance = article.get("relevance_score", 0) <= _RELEVANCE_EXCLUDE_THRESHOLD
        if low_relevance and not article.get("keyword_hints"):
            article["tier"] = "제외"

    return articles
```

- [ ] **Step 15: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step3_classify.py -v`
Expected: 전부 PASS

- [ ] **Step 16: 전체 회귀 테스트**

Run: `python -m pytest tests/ -v`
Expected: 전체 스위트 PASS (step2/step3 외 다른 Step 테스트에 영향 없어야 함)

- [ ] **Step 17: 커밋**

```bash
git add src/step3_classify.py tests/test_step3_classify.py
git commit -m "feat: force-exclude low-relevance articles with no keyword hints"
```
