import json
from unittest.mock import patch

import pytest

from src import gemini_client


class _Resp:
    def __init__(self, payload):
        self.text = json.dumps(payload)


class _FakeModels:
    """model 인자별로 성공/실패를 다르게 흉내 내는 가짜 client.models."""

    def __init__(self, behavior):
        self.behavior = behavior  # {model: Exception | dict}
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self.behavior[model]
        if isinstance(outcome, Exception):
            raise outcome
        return _Resp(outcome)


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _patch_client(models):
    return patch.object(gemini_client, "_get_client", lambda: _FakeClient(models))


@pytest.fixture(autouse=True)
def _no_sleep():
    # 재시도 backoff/throttle로 테스트가 느려지지 않게 무력화한다.
    with patch.object(gemini_client.time, "sleep", lambda *_: None), patch.object(
        gemini_client, "_throttle", lambda: None
    ):
        yield


def test_call_gemini_returns_parsed_json_on_success():
    models = _FakeModels({gemini_client.LITE_MODEL: {"ok": True}})
    with _patch_client(models):
        result = gemini_client.call_gemini("p", {}, model=gemini_client.LITE_MODEL)
    assert result == {"ok": True}
    assert models.calls == [gemini_client.LITE_MODEL]


def test_call_gemini_falls_back_to_other_tier_on_overload():
    # LITE가 503으로 계속 실패하면 FLASH(DEFAULT)로 폴백해 성공한다.
    models = _FakeModels(
        {
            gemini_client.LITE_MODEL: RuntimeError("503 UNAVAILABLE: high demand"),
            gemini_client.DEFAULT_MODEL: {"ok": "from_flash"},
        }
    )
    with _patch_client(models):
        result = gemini_client.call_gemini("p", {}, model=gemini_client.LITE_MODEL)
    assert result == {"ok": "from_flash"}
    assert gemini_client.DEFAULT_MODEL in models.calls


def test_call_gemini_raises_when_both_tiers_overloaded():
    models = _FakeModels(
        {
            gemini_client.LITE_MODEL: RuntimeError("503 UNAVAILABLE"),
            gemini_client.DEFAULT_MODEL: RuntimeError("503 UNAVAILABLE"),
        }
    )
    with _patch_client(models):
        with pytest.raises(RuntimeError, match="호출 실패"):
            gemini_client.call_gemini("p", {}, model=gemini_client.LITE_MODEL)


def test_call_gemini_does_not_fall_back_on_daily_quota():
    # PerDay(일일 할당량 소진)는 다른 티어로도 회복되지 않으므로 폴백하지 않는다.
    models = _FakeModels(
        {
            gemini_client.LITE_MODEL: RuntimeError("429 RESOURCE_EXHAUSTED: PerDay limit"),
            gemini_client.DEFAULT_MODEL: {"ok": "should_not_reach"},
        }
    )
    with _patch_client(models):
        with pytest.raises(RuntimeError, match="호출 실패"):
            gemini_client.call_gemini("p", {}, model=gemini_client.LITE_MODEL)
    assert gemini_client.DEFAULT_MODEL not in models.calls
