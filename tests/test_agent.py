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
    # No Windows o claude pode ser um .cmd, que corta argumentos com quebra de linha.
    assert kwargs["input"].startswith("criar hello.py\n")
    assert not any("\n" in arg for arg in args)
    # Pode editar nas pastas do usuário, mas nunca roda comandos.
    assert args[args.index("--disallowedTools") + 1] == "Bash"


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


def test_action_is_not_repeated_when_reporting_the_result_fails(monkeypatch):
    opened = []
    sent = []
    monkeypatch.setattr(agent.subprocess, "Popen", opened.append)
    monkeypatch.setattr(agent, "unreported", {})

    def post(url, json, headers, timeout):
        sent.append(json)
        if len(sent) == 1:
            raise agent.requests.ConnectionError("sem rede")

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"success": True}

        return Response()

    monkeypatch.setattr(agent.requests, "post", post)

    with pytest.raises(agent.requests.ConnectionError):
        agent.execute_command(9, "open_app:notepad")

    # O comando continua pendente na API; na próxima consulta só o resultado é reenviado.
    agent.execute_command(9, "open_app:notepad")

    assert len(opened) == 1
    assert sent == [{"status": "completed", "result": "Bloco de Notas aberto"}] * 2
    assert agent.unreported == {}


def test_only_one_agent_runs_per_computer(monkeypatch):
    monkeypatch.setattr(agent, "AGENT_TOKEN", "segredo")
    monkeypatch.setattr(agent, "LOCK_PORT", 0)
    first = agent.start()
    monkeypatch.setattr(agent, "LOCK_PORT", first.getsockname()[1])

    try:
        assert agent.start() == "outro agente já está rodando neste computador"
    finally:
        first.close()


def test_agent_needs_token(monkeypatch):
    monkeypatch.setattr(agent, "AGENT_TOKEN", None)

    assert "AGENT_TOKEN" in agent.start()


def test_serve_polls_until_stopped(monkeypatch):
    import threading

    stop = threading.Event()
    polls = []

    def check():
        polls.append(1)
        stop.set()

    monkeypatch.setattr(agent, "check_commands", check)

    class Lock:
        closed = False

        def close(self):
            self.closed = True

    lock = Lock()
    agent.serve(lock, stop)

    assert polls == [1]
    assert lock.closed
