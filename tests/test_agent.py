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


class Completed:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def claude(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(agent, "JARVIS_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(agent.shutil, "which", lambda name: "/bin/claude")

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return Completed(0, "Criei hello.py.")

    monkeypatch.setattr(agent.subprocess, "run", run)
    return calls


def test_claude_code_runs_inside_workspace_without_bash(claude, tmp_path):
    assert agent.call_claude_code("criar hello.py") == ("completed", "Criei hello.py.")

    args, kwargs = claude[0]
    assert kwargs["cwd"] == str(tmp_path)
    assert args[args.index("--allowedTools") + 1] == "Read,Edit,Write,Glob,Grep"


def test_claude_code_needs_workspace(claude, monkeypatch):
    monkeypatch.setattr(agent, "JARVIS_WORKSPACE", None)

    assert agent.call_claude_code("x")[0] == "failed"
    assert claude == []


def test_claude_code_missing_is_failed(claude, monkeypatch):
    monkeypatch.setattr(agent.shutil, "which", lambda name: None)

    assert agent.call_claude_code("x")[0] == "failed"


def test_claude_code_error_is_failed(claude, monkeypatch):
    monkeypatch.setattr(agent.subprocess, "run", lambda args, **kwargs: Completed(1, stderr="sem login"))

    assert agent.call_claude_code("x") == ("failed", "sem login")


def test_claude_code_command_runs_once_while_pending(finished, monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            started.append(args)

        def start(self):
            pass

    monkeypatch.setattr(agent.threading, "Thread", FakeThread)
    monkeypatch.setattr(agent, "running_ids", set())

    agent.execute_command(9, "claude_code:criar hello.py")
    agent.execute_command(9, "claude_code:criar hello.py")

    assert started == [(9, "criar hello.py")]


def test_background_run_reports_and_clears(finished, monkeypatch):
    monkeypatch.setattr(agent, "call_claude_code", lambda task: ("completed", "feito"))
    monkeypatch.setattr(agent, "running_ids", {9})

    agent.run_claude_code(9, "criar hello.py")

    assert finished == [(9, "completed", "feito")]
    assert agent.running_ids == set()
