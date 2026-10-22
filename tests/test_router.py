import pytest

from router import detect_command, is_allowed_command


@pytest.mark.parametrize("question, command", [
    ("abra o bloco de notas", "open_app:notepad"),
    ("Abrir o Bloco de Notas", "open_app:notepad"),
    ("jarvis, abre o notepad por favor", "open_app:notepad"),
    ("inicie o bloco de notas", "open_app:notepad"),
    ("abra o WhatsApp", "open_website:whatsapp"),
    ("abre o zap", "open_website:whatsapp"),
    ("pode abrir o whats app", "open_website:whatsapp"),
])
def test_detects_known_commands(question, command):
    assert detect_command(question)[0] == command


@pytest.mark.parametrize("question", [
    "o que é o bloco de notas",
    "como abrir o bloco de notas",
    "quem criou o whatsapp",
    "qual a previsão do tempo",
    "abra a calculadora",
    "fale sobre a abertura dos jogos",
])
def test_ignores_questions_and_unknown_commands(question):
    assert detect_command(question) is None


@pytest.mark.parametrize("question, task", [
    ("Peça ao Claude para criar um script que soma dois números", "criar um script que soma dois números"),
    ("jarvis, manda pro claude code pra criar hello.py", "criar hello.py"),
    ("pede pro Claude que Faça Testes", "Faça Testes"),
])
def test_detects_claude_code_tasks(question, task):
    assert detect_command(question)[0] == f"claude_code:{task}"


@pytest.mark.parametrize("command, allowed", [
    ("open_app:notepad", True),
    ("claude_code:criar hello.py", True),
    ("claude_code:   ", False),
    ("claude_code:" + "x" * 1001, False),
    ("cmd:del C:\\", False),
])
def test_is_allowed_command(command, allowed):
    assert is_allowed_command(command) is allowed
