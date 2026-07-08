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

_client = None
_last_call_at = 0.0


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


def call_gemini(prompt: str, response_schema: dict, model: str = DEFAULT_MODEL) -> dict:
    """Gemini API를 호출해 구조화된 JSON 출력을 반환한다.

    response_mime_type="application/json" + 스키마 지정으로 구조화 출력을 강제한다.
    429/일시 오류 시 exponential backoff로 재시도하며, 무료 티어 한도(분당 15~30회)를
    감안해 요청 간 최소 간격을 둔다.

    Args:
        prompt: Gemini에 전달할 프롬프트
        response_schema: 강제할 JSON 스키마
        model: 사용할 모델명 (gemini-2.5-flash 또는 gemini-2.5-flash-lite)

    Returns:
        파싱된 JSON 응답 dict

    Raises:
        RuntimeError: 재시도 후에도 호출 실패 시
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

    raise RuntimeError(f"Gemini API 호출 실패 ({_MAX_RETRIES}회 재시도): {last_error}") from last_error
