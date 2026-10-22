import pytest

from router import detect_command


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
