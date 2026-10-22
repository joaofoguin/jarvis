import pytest

from agent import agent


@pytest.fixture
def finished(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "finish_command", lambda *args: calls.append(args))
    monkeypatch.setattr(agent.subprocess, "Popen", lambda args: None)
    return calls


def test_allowed_command_is_completed(finished):
    agent.execute_command(1, "open_app:notepad")

    assert finished == [(1, "completed", "Bloco de Notas aberto")]


def test_unknown_command_is_rejected(finished):
    agent.execute_command(2, "rm -rf /")

    assert finished == [(2, "rejected", "Comando não está na lista permitida")]


def test_action_error_is_failed(finished, monkeypatch):
    def broken(args):
        raise FileNotFoundError("notepad.exe")

    monkeypatch.setattr(agent.subprocess, "Popen", broken)

    agent.execute_command(3, "open_app:notepad")

    assert finished[0][:2] == (3, "failed")
