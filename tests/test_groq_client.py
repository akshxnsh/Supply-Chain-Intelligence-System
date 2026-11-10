"""Groq client and model routing (no network: a fake HTTP session)."""

import json

import pytest
import requests

from src.reader import client as client_mod
from src.reader.groq_client import MAX_COMPLETION_TOKENS, GroqClient
from src.reader.limiter import LLMError, call_with_retry, is_retryable


class Resp:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, text or json.dumps(body or {})

    def json(self):
        return self._body


class Session:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


OK = {"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"prompt_tokens": 880, "completion_tokens": 490}}


def test_request_shape_and_response_parsing():
    s = Session(Resp(200, OK))
    out = GroqClient("gsk_test", session=s).generate("hello", "openai/gpt-oss-120b", temperature=0.1, max_output_tokens=8192)
    call = s.calls[0]
    assert call["url"].endswith("/chat/completions") and call["headers"]["Authorization"] == "Bearer gsk_test"
    assert call["json"]["model"] == "openai/gpt-oss-120b" and call["json"]["response_format"] == {"type": "json_object"}
    assert call["json"]["max_completion_tokens"] == MAX_COMPLETION_TOKENS and call["json"]["messages"][0]["content"] == "hello"
    assert out.text == '{"ok": true}' and out.input_tokens == 880 and out.output_tokens == 490 and out.latency_ms >= 0


def test_rate_limit_error_carries_retry_after_and_is_retried():
    err = Resp(429, headers={"retry-after": "7"}, text="rate limit")
    s = Session(err)
    with pytest.raises(LLMError) as e:
        GroqClient("k", session=s).generate("x", "m")
    assert e.value.status_code == 429 and e.value.retry_after == 7.0 and is_retryable(e.value)
    sleeps, seq = [], [Resp(429, headers={"retry-after": "2"}), Resp(200, OK)]

    class Seq(Session):
        def post(self, *a, **k):
            return seq.pop(0)

    r = call_with_retry(lambda: GroqClient("k", session=Seq(None)).generate("x", "m"), sleep=sleeps.append, jitter=lambda: 0.0)
    assert r.text == '{"ok": true}' and sleeps == [2.0]


def test_auth_error_timeout_and_missing_key(monkeypatch):
    with pytest.raises(LLMError) as e:
        GroqClient("bad", session=Session(Resp(401, text="invalid key"))).generate("x", "m")
    assert e.value.status_code == 401 and not is_retryable(e.value)
    with pytest.raises(LLMError) as e:
        GroqClient("k", session=Session(requests.Timeout())).generate("x", "m")
    assert e.value.status_code is None and is_retryable(e.value)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError) as e:
        GroqClient()
    assert e.value.status_code == 401 and "GROQ_API_KEY" in str(e.value)


def test_model_name_decides_the_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    assert isinstance(client_mod.make_client("openai/gpt-oss-120b"), GroqClient)
    assert isinstance(client_mod.make_client("qwen/qwen3.8-27b"), GroqClient)

    class FakeGemini:
        pass

    monkeypatch.setattr(client_mod, "GeminiClient", FakeGemini)
    assert isinstance(client_mod.make_client("gemini-3.5-flash-lite"), FakeGemini)


def test_reader_stays_on_gemini():
    from src.agent.model_config import READER_MODEL

    assert "/" not in READER_MODEL     # Groq's 8,000 tokens/min is too small for the reader's batches
