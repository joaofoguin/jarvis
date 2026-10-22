import json
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

# WhatsApp e Instagram pelo navegador (só na janela de chat do notebook).
WHATSAPP_PREFIX = "whatsapp_enviar:"
WHATSAPP_MAX_MESSAGE = 1000
INSTAGRAM_MESSAGES = "instagram_mensagens"
BROWSER_ANSWER = "Um momento, senhor. Estou abrindo o navegador."

WHATSAPP_APP = r"(whatsapp|whats app|zap)"
WHATSAPP_PATTERN = re.compile(
    rf"^(jarvis,? )?(mand[ae]|envi[ae]|escrev[ae])( uma)?( mensagem| msg)?(?P<app1> no {WHATSAPP_APP})? "
    rf"(para|pra|pro|ao|à|a|o) (?P<contato>.+?)(?P<app2> no {WHATSAPP_APP})?(:|,| dizendo| falando| escrito| que)\s+"
    r"(?P<texto>.+)$",
    re.IGNORECASE
)
INSTAGRAM_PATTERN = re.compile(r"\b(insta(gram)?|direct)\b.*\bmensage|\bmensage.*\b(insta(gram)?|direct)\b")

# Contatos do iPhone, lidos do iCloud (só na janela de chat do notebook).
ICLOUD_CONTACT_PREFIX = "icloud_contato:"

CONTACT_PATTERN = re.compile(
    r"\b(numero|telefone|celular|contato)( de telefone| do celular)? (da|do|de) (?P<nome>[\w ]+?)\s*\??$"
)

# Memória do JARVIS: o que o usuário ensina no chat fica em arquivos (só no notebook).
MEMORY_PREFIX = "memoria_lembrar:"
FORGET_PREFIX = "memoria_esquecer:"
MEMORY_MAX_FACT = 300

LEARN_PATTERN = re.compile(
    r"^(jarvis,? )?(lembr[ae](-se)?|aprend[ae]|guard[ae]|anot[ae]|memoriz[ae])( de| isso)?( que|:)\s*(?P<fato>.+)$",
    re.IGNORECASE
)
FORGET_PATTERN = re.compile(r"^(jarvis,? )?(esque[cç]a|esquece)( que| de| sobre)?\s+(?P<fato>.+)$", re.IGNORECASE)

# Perguntas sobre o programa não são ordens para abri-lo.
QUESTION_PREFIXES = ("como ", "o que ", "por que ", "porque ", "qual ", "quando ")


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def plain(text):
    """Texto normalizado só com letras, números e espaços (tira emojis e pontuação de nomes)."""

    return " ".join(re.sub(r"[^\w ]", " ", normalize(text)).split())


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


def whatsapp_command(contact, message):
    contact = " ".join(str(contact).split())
    message = str(message).strip()

    if not contact or not message or len(contact) > 60 or len(message) > WHATSAPP_MAX_MESSAGE:
        return None

    return WHATSAPP_PREFIX + json.dumps([contact, message], ensure_ascii=False), BROWSER_ANSWER


def whatsapp_args(command):
    """Retorna (contato, mensagem) de um comando whatsapp_enviar."""

    return tuple(json.loads(command[len(WHATSAPP_PREFIX):]))


def detect_browser(question):
    """Reconhece pedidos de WhatsApp e Instagram sem IA. Retorna (comando, resposta) ou None."""

    match = WHATSAPP_PATTERN.match(" ".join(question.split()))

    # Sem citar o WhatsApp, a frase pode ser outra coisa; nesse caso a IA decide.
    if match and (match["app1"] or match["app2"]):
        return whatsapp_command(match["contato"], match["texto"])

    if INSTAGRAM_PATTERN.search(normalize(question)):
        return INSTAGRAM_MESSAGES, BROWSER_ANSWER

    return None


def contact_command(name):
    name = " ".join(str(name).split())[:60]
    return (ICLOUD_CONTACT_PREFIX + name, GOOGLE_ANSWER) if name else None


def detect_contact(question):
    """Reconhece "qual o número da X" sem IA. Retorna (comando, resposta) ou None."""

    match = CONTACT_PATTERN.search(normalize(question))
    return contact_command(match["nome"]) if match else None


def memory_command(prefix, fact):
    fact = " ".join(str(fact).split())
    return (prefix + fact, "") if 0 < len(fact) <= MEMORY_MAX_FACT else None


def detect_memory(question):
    """Reconhece "lembre que ..." e "esqueça que ..." sem IA. Retorna (comando, resposta) ou None."""

    text = " ".join(question.split())
    learn = LEARN_PATTERN.match(text)

    if learn:
        return memory_command(MEMORY_PREFIX, learn["fato"])

    forget = FORGET_PATTERN.match(text)
    return memory_command(FORGET_PREFIX, forget["fato"]) if forget else None


def command_for_tool(name, arguments):
    """Converte uma ferramenta escolhida pela IA em (comando, resposta falada), ou None."""

    if name == "ver_agenda":
        return agenda_command(arguments.get("dias", 1))

    if name == "ver_tarefas_classroom":
        return GOOGLE_CLASSROOM, GOOGLE_ANSWER

    if name == "ver_youtube":
        return GOOGLE_YOUTUBE, GOOGLE_ANSWER

    if name == "enviar_whatsapp":
        return whatsapp_command(arguments.get("contato", ""), arguments.get("mensagem", ""))

    if name == "ver_mensagens_instagram":
        return INSTAGRAM_MESSAGES, BROWSER_ANSWER

    if name == "buscar_contato":
        return contact_command(arguments.get("nome", ""))

    if name == "lembrar":
        return memory_command(MEMORY_PREFIX, arguments.get("fato", ""))

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
