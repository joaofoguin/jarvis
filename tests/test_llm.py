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

    assert llm.ask_llm("oi", "jarvis") == ("Olá, senhor.", None)
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


def tool_call_response(name, arguments):
    return lambda *args, **kwargs: FakeResponse({
        "choices": [{"message": {
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}]
        }}],
        "usage": {}
    })


def test_tool_call_becomes_command(monkeypatch):
    monkeypatch.setattr(llm, "log_usage", lambda *args: None)
    monkeypatch.setattr(llm.requests, "post", tool_call_response("open_notepad", "{}"))

    assert llm.ask_llm("preciso anotar algo", "alexa") == ("Abrindo o Bloco de Notas, senhor.", "open_app:notepad")


def test_claude_code_tool_carries_task(monkeypatch):
    monkeypatch.setattr(llm, "log_usage", lambda *args: None)
    monkeypatch.setattr(llm.requests, "post", tool_call_response("claude_code", '{"task": "criar hello.py"}'))

    answer, command = llm.ask_llm("cria um hello world em python", "alexa")

    assert command == "claude_code:criar hello.py"


def test_unknown_tool_without_text_is_an_error(monkeypatch):
    monkeypatch.setattr(llm, "log_usage", lambda *args: None)
    monkeypatch.setattr(llm.requests, "post", tool_call_response("format_disk", "{}"))

    with pytest.raises(llm.LLMError):
        llm.ask_llm("formate o disco", "alexa")


def test_tools_are_sent_to_deepseek(monkeypatch):
    sent = {}
    monkeypatch.setattr(llm, "log_usage", lambda *args: None)

    def post(url, **kwargs):
        sent.update(kwargs["json"])
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    llm.ask_llm("oi", "jarvis")

    assert {t["function"]["name"] for t in sent["tools"]} == {"open_notepad", "open_whatsapp", "claude_code"}


def test_history_goes_between_system_and_question(monkeypatch):
    sent = {}
    monkeypatch.setattr(llm, "log_usage", lambda *args: None)

    def post(url, **kwargs):
        sent.update(kwargs["json"])
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    history = [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"}]

    llm.ask_llm("tudo bem?", "desktop", history)

    assert [m["content"] for m in sent["messages"][1:]] == ["oi", "olá", "tudo bem?"]
