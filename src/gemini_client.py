"""Gemini API 공통 호출 래퍼."""

import json
import os
import time

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-2.5-flash"
LITE_MODEL = "gemini-2.5-flash-lite"

_MAX_RETRIES = 5
_MIN_INTERVAL_SEC = 2.0  # 무료 티어 분당 15~30회 한도 감안

# 서버 과부하(503/UNAVAILABLE)는 할당량 소진과 달리 일시적이며, 모델 티어별로 용량이
# 따로라 한쪽이 막혀도 다른 쪽은 뚫리는 경우가 많다. 그래서 과부하로 재시도가 모두
# 실패하면 반대 티어로 한 번 더 시도한다.
_OVERLOAD_MARKERS = ("503", "UNAVAILABLE", "overloaded", "high demand")
_FALLBACK_MODEL = {LITE_MODEL: DEFAULT_MODEL, DEFAULT_MODEL: LITE_MODEL}

_client = None
_last_call_at = 0.0


def _is_overload_error(exc: Exception) -> bool:
    text = str(exc)
    return any(marker in text for marker in _OVERLOAD_MARKERS)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _throttle() -> None:
    global _last_call_at
    elapsed = time.monotonic() - _last_call_at
    if elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _last_call_at = time.monotonic()


def call_gemini(
    prompt: str, response_schema: dict, model: str = DEFAULT_MODEL, _allow_fallback: bool = True
) -> dict:
    """Gemini API를 호출해 구조화된 JSON 출력을 반환한다.

    response_mime_type="application/json" + 스키마 지정으로 구조화 출력을 강제한다.
    429/일시 오류 시 exponential backoff로 재시도하며, 무료 티어 한도(분당 15~30회)를
    감안해 요청 간 최소 간격을 둔다. 서버 과부하(503)로 재시도가 모두 실패하면 반대
    모델 티어로 한 번 더 시도한다(모델별 용량이 따로라 한쪽이 막혀도 다른 쪽은 뚫림).

    Args:
        prompt: Gemini에 전달할 프롬프트
        response_schema: 강제할 JSON 스키마
        model: 사용할 모델명 (gemini-2.5-flash 또는 gemini-2.5-flash-lite)
        _allow_fallback: 과부하 시 반대 티어 재시도 허용 여부 (재귀 무한루프 방지용 내부 인자)

    Returns:
        파싱된 JSON 응답 dict

    Raises:
        RuntimeError: 재시도(및 폴백)까지 모두 실패 시
    """
    client = _get_client()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        _throttle()
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            return json.loads(response.text)
        except Exception as exc:  # noqa: BLE001 - 429/일시 오류 재시도 후 RuntimeError로 래핑
            last_error = exc
            if "PerDay" in str(exc):
                # 일일 무료 할당량 소진 - 분 단위 재시도로는 회복되지 않으므로 즉시 포기
                break
            time.sleep(2**attempt)

    if _allow_fallback and last_error is not None and _is_overload_error(last_error):
        fallback = _FALLBACK_MODEL.get(model)
        if fallback:
            return call_gemini(prompt, response_schema, model=fallback, _allow_fallback=False)

    raise RuntimeError(f"Gemini API 호출 실패 ({_MAX_RETRIES}회 재시도): {last_error}") from last_error
