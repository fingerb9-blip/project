"""Gemini API 공통 호출 래퍼."""

import os


DEFAULT_MODEL = "gemini-2.5-flash"
LITE_MODEL = "gemini-2.5-flash-lite"


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
    # TODO: google-genai SDK 사용, api_key = os.environ["GEMINI_API_KEY"]
    raise NotImplementedError
