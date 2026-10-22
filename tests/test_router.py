import pytest

from router import (
    FORGET_PREFIX, ICLOUD_CONTACT_PREFIX, INSTAGRAM_MESSAGES, MEMORY_PREFIX, WHATSAPP_PREFIX,
    command_for_tool, detect_browser, detect_command, detect_contact, detect_google, detect_memory, is_allowed_command,
    plain,
    whatsapp_args
)


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


@pytest.mark.parametrize("question, command", [
    ("o que tenho hoje?", "google_agenda:1"),
    ("tenho algum compromisso amanhã", "google_agenda:2"),
    ("minha agenda da semana", "google_agenda:7"),
    ("quais as tarefas pendentes", "google_classroom"),
    ("o que tem no Classroom", "google_classroom"),
])
def test_detects_google_requests(question, command):
    assert detect_google(question)[0] == command


@pytest.mark.parametrize("question", ["crie tarefas no código", "abra o bloco de notas"])
def test_ignores_non_google_requests(question):
    assert detect_google(question) is None


def test_agenda_tool_clamps_days():
    assert command_for_tool("ver_agenda", {"dias": 30})[0] == "google_agenda:7"
    assert command_for_tool("ver_agenda", {"dias": 0})[0] == "google_agenda:1"


@pytest.mark.parametrize("question", ["como estão os insights do meu vídeo", "métricas do meu canal", "abre meu youtube studio"])
def test_detects_youtube_requests(question):
    assert detect_google(question)[0] == "google_youtube"


@pytest.mark.parametrize("question, contact, message", [
    ("mande mensagem para minha namorada no whatsapp dizendo Oi amor, já estou em casa",
     "minha namorada", "Oi amor, já estou em casa"),
    ("Jarvis, manda uma mensagem pro Amor no zap: Oi amor, já estou em casa", "Amor", "Oi amor, já estou em casa"),
    ("envie no WhatsApp para Mãe: chego às 18h", "Mãe", "chego às 18h"),
])
def test_detects_whatsapp_messages(question, contact, message):
    command, _ = detect_browser(question)

    assert command.startswith(WHATSAPP_PREFIX)
    assert whatsapp_args(command) == (contact, message)


@pytest.mark.parametrize("question", [
    "mande mensagem para minha mãe dizendo oi",
    "abra o whatsapp",
    "o que é o instagram?",
])
def test_ignores_non_browser_requests(question):
    assert detect_browser(question) is None


def test_detects_instagram_messages():
    assert detect_browser("verifique se há novas mensagens no instagram")[0] == INSTAGRAM_MESSAGES
    assert detect_browser("tenho mensagem nova no insta?")[0] == INSTAGRAM_MESSAGES


def test_whatsapp_tool_validates_arguments():
    assert command_for_tool("enviar_whatsapp", {"contato": "Amor", "mensagem": ""}) is None
    assert whatsapp_args(command_for_tool("enviar_whatsapp", {"contato": "Amor", "mensagem": "oi"})[0]) == ("Amor", "oi")


@pytest.mark.parametrize("question, name", [
    ("qual o número da Amor?", "amor"),
    ("me passa o telefone do Pedro Amorim", "pedro amorim"),
    ("qual o celular da minha namorada", "minha namorada"),
])
def test_detects_contact_requests(question, name):
    assert detect_contact(question)[0] == ICLOUD_CONTACT_PREFIX + name


def test_contact_tool():
    assert command_for_tool("buscar_contato", {"nome": "Amor"})[0] == ICLOUD_CONTACT_PREFIX + "Amor"
    assert command_for_tool("buscar_contato", {"nome": " "}) is None


@pytest.mark.parametrize("question, prefix, fact", [
    ("lembre que minha namorada é a Amor", MEMORY_PREFIX, "minha namorada é a Amor"),
    ("Jarvis, aprenda que eu estudo na UENP", MEMORY_PREFIX, "eu estudo na UENP"),
    ("anote: meu time é o Corinthians", MEMORY_PREFIX, "meu time é o Corinthians"),
    ("esqueça que meu time é o Corinthians", FORGET_PREFIX, "meu time é o Corinthians"),
])
def test_detects_memory_requests(question, prefix, fact):
    assert detect_memory(question)[0] == prefix + fact


def test_reminder_without_que_is_not_memory():
    assert detect_memory("lembre de pagar a conta") is None


def test_plain_drops_emojis_and_accents():
    assert plain("Amor❤️🥵") == "amor"
    assert plain("  Mãe  (casa) ") == "mae casa"


def test_remember_tool_with_contact_alias():
    command, _ = command_for_tool("lembrar", {"fato": "toninho é Toninho Hajime", "apelido": "toninho", "contato": "Toninho Hajime"})

    assert command == 'memoria_apelido:["toninho", "Toninho Hajime"]'
    assert command_for_tool("lembrar", {"fato": "eu sou o Foguinho"})[0] == "memoria_lembrar:eu sou o Foguinho"
