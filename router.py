import json
import re
import unicodedata
from datetime import datetime


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
# Pedidos que mudam a agenda ("adicione", "marque", "apague"...) vão para a IA, que tem criar/mudar/apagar_evento.
# A regra fixa da agenda só responde consultas.
AGENDA_CHANGE_PATTERN = re.compile(
    r"\b(adicion|acrescent|anot|registr|cri|mud|alter|cancel|apag|remov)(a|e|ar)\b"
    r"|\b(agend|marc|remarc|desmarc|coloc)(e|ar)\b|\b(marc|remarc|desmarc|coloc)a\b"
    r"|\b(apagu|marqu|remarqu|desmarqu|coloqu)e\b|\b(inclu|exclu)(a|i|ir)\b|\b(mov|tir)(a|e|er|ar)\b"
    r"|\b(bot(a|e|ar)|poe|ponha)\b"
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

# Google Drive (só na janela de chat do notebook). Editar sempre pede um "sim" antes.
DRIVE_PREFIX = "google_drive:"
DRIVE_READS = {"buscar", "ler", "baixar"}
DRIVE_EDITS = {"acrescentar", "substituir", "renomear"}
DRIVE_MAX_NAME = 200
DRIVE_MAX_TEXT = 1000

DRIVE_PATTERN = re.compile(
    r"^(jarvis,? )?(?P<verbo>procur[ae]|busc[ae]|baix[ae]|baixar|leia|le|ler)( o| a| os| as)?"
    r"( arquivos?| documentos?| planilhas?| apresentac(ao|oes))? (?P<nome>.+?) (no|do|da) (meu )?(google )?drive\W*$"
)
DRIVE_VERBS = {"procur": "buscar", "busc": "buscar", "baix": "baixar", "le": "ler"}

# Contatos do iPhone, lidos do iCloud (só na janela de chat do notebook).
ICLOUD_CONTACT_PREFIX = "icloud_contato:"

CONTACT_PATTERN = re.compile(
    r"\b(numero|telefone|celular|contato)( de telefone| do celular)? (da|do|de) (?P<nome>[\w ]+?)\s*\??$"
)

# Memória do JARVIS: a IA guarda e apaga itens (assunto, chave, valor), só no notebook.
CALENDAR_PREFIX = "google_evento:"
CALENDAR_ACTIONS = {"criar", "mudar", "apagar"}
GOOGLE_OPEN_PREFIX = "google_abrir:"

LOCAL_FILE_PREFIX = "arquivo_local:"
LOCAL_FILE_ACTIONS = {"abrir", "apagar"}
LOCAL_FILE_MAX_NAME = 200

MEMORY_PREFIX = "memoria_lembrar:"
FORGET_PREFIX = "memoria_esquecer:"
MEMORY_MAX_TEXT = 300

# Perguntas sobre o programa não são ordens para abri-lo.
HISTORY_LAST = "historico_apagar:ultimo"
HISTORY_CONVERSATION = "historico_apagar:conversa"
HISTORY_TODAY = "historico_apagar:hoje"

# "Esquecer" fica com a memória; aqui só apagar, excluir, deletar e limpar.
HISTORY_VERB = r"\b(apag|exclu|delet|limp)\w*\b"
HISTORY_TODAY_PATTERN = re.compile(HISTORY_VERB + r".*\b(disse|falei|pedi|conversas?|historico)\b.*\bhoje\b")
HISTORY_CONVERSATION_PATTERN = re.compile(HISTORY_VERB + r".*\b(ultima|essa|esta) conversa\b")
HISTORY_LAST_PATTERN = re.compile(
    HISTORY_VERB + r".*\b(acabei de (dizer|falar|pedir)|o que eu (disse|falei)|ultim[ao] (coisa|pedido|frase))\b"
)

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
    try:
        days = min(max(int(days), 1), 7)
    except (TypeError, ValueError):
        days = 1

    return f"{GOOGLE_AGENDA_PREFIX}{days}", GOOGLE_ANSWER


def detect_google(question):
    """Reconhece pedidos de agenda ou Classroom sem IA. Retorna (comando, resposta) ou None."""

    text = normalize(question)

    if YOUTUBE_PATTERN.search(text):
        return GOOGLE_YOUTUBE, GOOGLE_ANSWER

    if CLASSROOM_PATTERN.search(text):
        return GOOGLE_CLASSROOM, GOOGLE_ANSWER

    if AGENDA_PATTERN.search(text) and not AGENDA_CHANGE_PATTERN.search(text):
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


def drive_command(action, name, text="", new_text=""):
    """Comando do Drive com as partes em JSON, ou None se a ação ou os textos não servirem."""

    name, text, new_text = (" ".join(str(part).split()) for part in (name, text, new_text))

    if action not in DRIVE_READS | DRIVE_EDITS or not 0 < len(name) <= DRIVE_MAX_NAME:
        return None

    if action in DRIVE_EDITS and not 0 < len(text) <= DRIVE_MAX_TEXT or len(new_text) > DRIVE_MAX_TEXT:
        return None

    return DRIVE_PREFIX + json.dumps([action, name, text, new_text], ensure_ascii=False), GOOGLE_ANSWER


def calendar_command(action, event="", title="", start="", end="", account="", calendar=""):
    """Criar, mudar ou apagar um evento da agenda, ou None se faltar algo ou a data não servir.

    calendar: "google" para a Google Agenda; qualquer outro valor é o calendário do iPhone (iCloud).
    """

    calendar = "google" if str(calendar).lower() == "google" else "icloud"
    parts = [" ".join(str(part or "").split())[:200] for part in (event, title, start, end, account)] + [calendar]
    event, title, start, end, account, _ = parts

    try:
        for value in (start, end):
            if value:
                datetime.fromisoformat(value)
    except ValueError:
        return None

    needed = {"criar": title and start, "mudar": event and (title or start), "apagar": event}

    if action not in CALENDAR_ACTIONS or not needed[action]:
        return None

    return CALENDAR_PREFIX + json.dumps([action, *parts], ensure_ascii=False), GOOGLE_ANSWER


def calendar_args(command):
    """Retorna (ação, evento, título, início, fim, conta, agenda) de um comando google_evento."""

    return tuple(json.loads(command[len(CALENDAR_PREFIX):]))


def local_file_command(action, name):
    """Abrir ou apagar um arquivo da pasta de trabalho, ou None se não servir."""

    name = " ".join(str(name).split())

    if action not in LOCAL_FILE_ACTIONS or not 0 < len(name) <= LOCAL_FILE_MAX_NAME:
        return None

    return LOCAL_FILE_PREFIX + json.dumps([action, name], ensure_ascii=False), "Certo, senhor."


def local_file_args(command):
    """Retorna (ação, arquivo) de um comando arquivo_local."""

    return tuple(json.loads(command[len(LOCAL_FILE_PREFIX):]))


def drive_args(command):
    """Retorna (ação, arquivo, texto, novo texto) de um comando google_drive."""

    return tuple(json.loads(command[len(DRIVE_PREFIX):]))


def detect_history(question):
    """Pedidos para apagar o histórico de conversas do notebook. Retorna o comando ou None."""

    text = normalize(question)

    for pattern, command in [
        (HISTORY_TODAY_PATTERN, HISTORY_TODAY),
        (HISTORY_CONVERSATION_PATTERN, HISTORY_CONVERSATION),
        (HISTORY_LAST_PATTERN, HISTORY_LAST)
    ]:
        if pattern.search(text):
            return command

    return None


def detect_drive(question):
    """Reconhece "procure/baixe/leia X no Drive" sem IA. Retorna (comando, resposta) ou None."""

    original = " ".join(question.split())
    match = DRIVE_PATTERN.match(normalize(original))

    if not match:
        return None

    action = next(value for prefix, value in DRIVE_VERBS.items() if match["verbo"].startswith(prefix))
    # Pega o nome do texto original, mantendo maiúsculas e acentos.
    return drive_command(action, original[match.start("nome"):match.end("nome")])


def contact_command(name):
    name = " ".join(str(name).split())[:60]
    return (ICLOUD_CONTACT_PREFIX + name, GOOGLE_ANSWER) if name else None


def detect_contact(question):
    """Reconhece "qual o número da X" sem IA. Retorna (comando, resposta) ou None."""

    match = CONTACT_PATTERN.search(normalize(question))
    return contact_command(match["nome"]) if match else None


def memory_command(prefix, *parts):
    """Comando de memória com as partes em JSON, ou None se alguma parte estiver vazia ou longa demais."""

    parts = [" ".join(str(part).split()) for part in parts]

    if not all(0 < len(part) <= MEMORY_MAX_TEXT for part in parts):
        return None

    return prefix + json.dumps(parts, ensure_ascii=False), ""


def memory_args(command):
    prefix = MEMORY_PREFIX if command.startswith(MEMORY_PREFIX) else FORGET_PREFIX
    return json.loads(command[len(prefix):])


def command_for_tool(name, arguments):
    """Converte uma ferramenta escolhida pela IA em (comando, resposta falada), ou None."""

    # A IA pode mandar argumentos fora do formato (null, lista); nesse caso valem os padrões.
    if not isinstance(arguments, dict):
        arguments = {}

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

    if name in ("buscar_drive", "ler_arquivo_drive", "baixar_arquivo_drive"):
        action = {"buscar_drive": "buscar", "ler_arquivo_drive": "ler", "baixar_arquivo_drive": "baixar"}[name]
        return drive_command(action, arguments.get("arquivo", ""))

    if name == "editar_arquivo_drive":
        return drive_command(
            arguments.get("acao", ""), arguments.get("arquivo", ""), arguments.get("texto", ""), arguments.get("novo_texto", "")
        )

    if name in ("criar_evento", "mudar_evento", "apagar_evento"):
        return calendar_command(
            name.split("_")[0], arguments.get("evento", ""), arguments.get("titulo", ""),
            arguments.get("inicio", ""), arguments.get("fim", ""), arguments.get("conta", ""), arguments.get("agenda", "")
        )

    if name == "abrir_no_google" and str(arguments.get("item", "")).strip():
        return GOOGLE_OPEN_PREFIX + " ".join(str(arguments["item"]).split())[:200], GOOGLE_ANSWER

    if name in ("abrir_arquivo", "apagar_arquivo"):
        return local_file_command(name.split("_")[0], arguments.get("arquivo", ""))

    if name == "buscar_contato":
        return contact_command(arguments.get("nome", ""))

    if name == "lembrar":
        return memory_command(
            MEMORY_PREFIX, arguments.get("assunto", ""), arguments.get("chave", ""), arguments.get("valor", "")
        )

    if name == "esquecer":
        return memory_command(FORGET_PREFIX, arguments.get("assunto", ""), arguments.get("chave", ""))

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
