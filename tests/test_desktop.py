import pytest

from desktop import core
from llm import LLMError


@pytest.fixture
def actions(monkeypatch):
    executed = []
    monkeypatch.setattr(core, "run_action", executed.append)
    return executed


def test_known_command_runs_locally_without_ai(actions, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: pytest.fail("não deveria chamar a IA"))

    assert core.reply_to("abra o bloco de notas", []) == ("Abrindo o Bloco de Notas, senhor.", None)
    assert actions == ["open_app:notepad"]


def test_ai_answer_uses_recent_history(actions, monkeypatch):
    received = {}

    def ask(text, source, history):
        received["history"] = history
        return "Brasília, senhor.", None

    monkeypatch.setattr(core, "ask_llm", ask)
    history = [{"role": "user", "content": str(n)} for n in range(10)]

    assert core.reply_to("e a capital?", history) == ("Brasília, senhor.", None)
    assert received["history"] == history[-core.HISTORY_LIMIT:]
    assert actions == []


def test_ai_chosen_action_runs_locally(actions, monkeypatch):
    monkeypatch.setattr(core, "ask_llm", lambda *args: ("Abrindo, senhor.", "open_website:whatsapp"))

    core.reply_to("quero mandar mensagem para minha mãe", [])

    assert actions == ["open_website:whatsapp"]


def test_claude_code_task_is_returned_for_background(actions):
    answer, task = core.reply_to("peça ao Claude para criar ola.py", [])

    assert task == "criar ola.py"
    assert actions == []


def test_ai_failure_gives_friendly_answer(actions, monkeypatch):
    def fail(*args):
        raise LLMError("sem saldo")

    monkeypatch.setattr(core, "ask_llm", fail)

    assert core.reply_to("conte uma piada", [])[0].startswith("Desculpe, senhor.")


def test_action_failure_is_reported(monkeypatch):
    def broken(command):
        raise FileNotFoundError("notepad.exe")

    monkeypatch.setattr(core, "run_action", broken)

    assert "notepad.exe" in core.reply_to("abra o bloco de notas", [])[0]


def test_run_task_reports_result(monkeypatch):
    monkeypatch.setattr(core, "call_claude_code", lambda task: ("completed", "Criei ola.py."))

    assert core.run_task("criar ola.py") == "Claude Code terminou: Criei ola.py."
