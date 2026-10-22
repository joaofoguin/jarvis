import re
import unicodedata


# Comandos conhecidos são resolvidos aqui, sem gastar tokens de IA.
COMMANDS = [
    {
        "command": "open_app:notepad",
        "tool": "open_notepad",
        "description": "Abre o Bloco de Notas no computador do usuário.",
        "targets": ["bloco de notas", "notepad"],
        "answer": "Abrindo o Bloco de Notas, senhor."
    },
    {
        "command": "open_website:whatsapp",
        "tool": "open_whatsapp",
        "description": "Abre o WhatsApp Web no navegador do computador do usuário.",
        "targets": ["whatsapp", "whats app", "zap"],
        "answer": "Abrindo o WhatsApp Web, senhor."
    }
]

ALLOWED_COMMANDS = {item["command"] for item in COMMANDS}

# Tarefas de programação vão para o Claude Code no PC, como "claude_code:<tarefa>".
CLAUDE_CODE_PREFIX = "claude_code:"
CLAUDE_CODE_MAX_TASK = 1000
CLAUDE_CODE_ANSWER = "Certo, senhor. Pedi ao Claude Code para cuidar disso no computador."

CLAUDE_CODE_PATTERN = re.compile(
    r"^(jarvis,? )?(pe[cç][ao]|pede|mand[ae]|fal[ae]) (ao|pro|para o|pra o) claude( code)?,? "
    r"(para|pra|que) (?P<task>.+)$"
)

ACTION_PATTERN = re.compile(
    r"\b(abr(a|e|ir)|inici\w*|execut\w*|lanc\w*|carreg\w*)\b"
)

# Consultas ao Google (só na janela de chat do notebook, que tem o login do Google).
GOOGLE_AGENDA_PREFIX = "google_agenda:"
GOOGLE_CLASSROOM = "google_classroom"
GOOGLE_YOUTUBE = "google_youtube"
GOOGLE_ANSWER = "Um momento, senhor. Estou consultando."

AGENDA_PATTERN = re.compile(
    r"\b(agenda|compromissos?|eventos?|o que (eu )?tenho)\b"
)
YOUTUBE_PATTERN = re.compile(
    r"\b(youtube|insights?|(metricas|estatisticas|desempenho) do (meu )?(video|canal))\b"
)
CLASSROOM_PATTERN = re.compile(
    r"\b(classroom|(tarefas?|atividades?|trabalhos?) (pendentes?|para entregar|da faculdade))\b"
)

# Perguntas sobre o programa não são ordens para abri-lo.
QUESTION_PREFIXES = ("como ", "o que ", "por que ", "porque ", "qual ", "quando ")


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def is_allowed_command(command):
    if command in ALLOWED_COMMANDS:
        return True

    if command.startswith(CLAUDE_CODE_PREFIX):
        task = command[len(CLAUDE_CODE_PREFIX):].strip()
        return 0 < len(task) <= CLAUDE_CODE_MAX_TASK

    return False


def claude_code_command(task):
    return CLAUDE_CODE_PREFIX + task.strip()[:CLAUDE_CODE_MAX_TASK], CLAUDE_CODE_ANSWER


def agenda_command(days):
    days = min(max(int(days), 1), 7)
    return f"{GOOGLE_AGENDA_PREFIX}{days}", GOOGLE_ANSWER


def detect_google(question):
    """Reconhece pedidos de agenda ou Classroom sem IA. Retorna (comando, resposta) ou None."""

    text = normalize(question)

    if YOUTUBE_PATTERN.search(text):
        return GOOGLE_YOUTUBE, GOOGLE_ANSWER

    if CLASSROOM_PATTERN.search(text):
        return GOOGLE_CLASSROOM, GOOGLE_ANSWER

    if AGENDA_PATTERN.search(text):
        if "semana" in text:
            return agenda_command(7)

        if "amanha" in text:
            return agenda_command(2)

        return agenda_command(1)

    return None


def command_for_tool(name, arguments):
    """Converte uma ferramenta escolhida pela IA em (comando, resposta falada), ou None."""

    if name == "ver_agenda":
        return agenda_command(arguments.get("dias", 1))

    if name == "ver_tarefas_classroom":
        return GOOGLE_CLASSROOM, GOOGLE_ANSWER

    if name == "ver_youtube":
        return GOOGLE_YOUTUBE, GOOGLE_ANSWER

    for item in COMMANDS:
        if item["tool"] == name:
            return item["command"], item["answer"]

    if name == "claude_code" and str(arguments.get("task", "")).strip():
        return claude_code_command(arguments["task"])

    return None


def detect_command(question):
    """Retorna (comando, resposta falada) ou None se não for um comando conhecido."""

    claude_match = CLAUDE_CODE_PATTERN.match(" ".join(question.split()).lower())

    if claude_match:
        # Pega a tarefa do texto original, mantendo maiúsculas e acentos.
        task = " ".join(question.split())[claude_match.start("task"):]
        return claude_code_command(task)

    text = normalize(question)

    if text.startswith(QUESTION_PREFIXES):
        return None

    if not ACTION_PATTERN.search(text):
        return None

    for item in COMMANDS:
        for target in item["targets"]:
            if re.search(rf"\b{re.escape(target)}\b", text):
                return item["command"], item["answer"]

    return None
