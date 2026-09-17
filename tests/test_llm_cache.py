"""Tests for the content-addressed LLM cache and OpenRouter retry logic."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from usdm4_assure.llm.cache import LLMCache, cache_key
from usdm4_assure.llm.openrouter import OpenRouterLLM


def test_cache_key_stable_for_identical_inputs():
    messages = [{"role": "user", "content": "hello"}]
    assert cache_key("m", messages, 100) == cache_key("m", messages, 100)


def test_cache_key_differs_on_any_input(tmp_path):
    base = [{"role": "user", "content": "hello"}]
    assert cache_key("m1", base, 100) != cache_key("m2", base, 100)
    assert cache_key("m", base, 100) != cache_key("m", base, 200)
    other = [{"role": "user", "content": "goodbye"}]
    assert cache_key("m", base, 100) != cache_key("m", other, 100)


def test_cache_put_get_roundtrip(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    key = cache_key("m", [{"role": "user", "content": "x"}], 100)
    assert cache.get(key) is None
    cache.put(key, model="m", prompt_hash=key, response="the answer")
    assert cache.get(key) == "the answer"


def test_cache_miss_then_hit_avoids_second_http_call(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache)
    llm.api_key = "fake-key"
    llm.available = True

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "cached answer"}}]
    }
    with patch("usdm4_assure.llm.openrouter.requests.post",
               return_value=fake_response) as mock_post:
        first = llm.complete("hello")
        second = llm.complete("hello")

    assert first == "cached answer"
    assert second == "cached answer"
    assert mock_post.call_count == 1  # second call served from cache


def test_retry_on_429_then_succeeds(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache, timeout=1.0)
    llm.api_key = "fake-key"
    llm.available = True

    rate_limited = Mock(status_code=429, text="rate limited")
    ok = Mock(status_code=200)
    ok.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("usdm4_assure.llm.openrouter.requests.post",
               side_effect=[rate_limited, ok]) as mock_post, \
         patch("usdm4_assure.llm.openrouter.time.sleep") as mock_sleep:
        result = llm.complete("hello")

    assert result == "ok"
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once()


def test_non_retryable_error_raises_immediately(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache, timeout=1.0)
    llm.api_key = "fake-key"
    llm.available = True

    bad_request = Mock(status_code=400, text="bad request")
    with patch("usdm4_assure.llm.openrouter.requests.post",
               return_value=bad_request) as mock_post, pytest.raises(RuntimeError, match="400"):
        llm.complete("hello")

    assert mock_post.call_count == 1  # no retry on a non-retryable status


def test_exhausts_retries_and_raises(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache, timeout=1.0)
    llm.api_key = "fake-key"
    llm.available = True

    server_error = Mock(status_code=503, text="unavailable")
    with (
        patch("usdm4_assure.llm.openrouter.requests.post", return_value=server_error) as mock_post,
        patch("usdm4_assure.llm.openrouter.time.sleep"),
        pytest.raises(RuntimeError, match="failed after 4 attempts"),
    ):
        llm.complete("hello")

    assert mock_post.call_count == 4
