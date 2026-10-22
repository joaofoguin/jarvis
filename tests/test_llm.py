import pytest
import requests

import llm


class FakeResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"status {self.status}")

    def json(self):
        return self.data


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "teste")


def test_returns_answer_and_logs_usage(monkeypatch):
    logged = []
    monkeypatch.setattr(llm, "log_usage", lambda *args: logged.append(args))
    monkeypatch.setattr(llm.requests, "post", lambda *args, **kwargs: FakeResponse({
        "model": "deepseek-chat",
        "choices": [{"message": {"content": "  Olá, senhor.  "}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 5}
    }))

    assert llm.ask_llm("oi", "jarvis") == "Olá, senhor."
    assert logged == [("jarvis", "deepseek-chat", {"prompt_tokens": 50, "completion_tokens": 5})]


def test_http_error_becomes_llm_error(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *args, **kwargs: FakeResponse({}, 402))

    with pytest.raises(llm.LLMError):
        llm.ask_llm("oi", "jarvis")


def test_missing_key_becomes_llm_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")

    with pytest.raises(llm.LLMError):
        llm.ask_llm("oi", "jarvis")


def test_log_usage_never_raises(monkeypatch):
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    llm.log_usage("jarvis", "deepseek-chat", {"prompt_tokens": 1})
