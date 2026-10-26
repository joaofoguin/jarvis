import browser
import drive_data
import google_data
import icloud_data
import memory
import reports
import whatsapp_app

from agent.agent import call_claude_code, run_action
from llm import BROWSER_TOOLS, GOOGLE_TOOLS, ICLOUD_TOOLS, MEMORY_TOOLS, TOOLS, LLMError, ask_llm
from router import (
    CLAUDE_CODE_PREFIX, DRIVE_PREFIX, DRIVE_READS, FORGET_PREFIX, GOOGLE_AGENDA_PREFIX, GOOGLE_CLASSROOM, GOOGLE_YOUTUBE,
    ICLOUD_CONTACT_PREFIX, INSTAGRAM_MESSAGES, MEMORY_PREFIX, WHATSAPP_PREFIX,
    detect_browser, detect_command, detect_contact, detect_drive, detect_google, drive_args, memory_args, normalize,
    plain, whatsapp_args
)


# Mensagens anteriores enviadas à IA. Mais contexto custa mais tokens.
HISTORY_LIMIT = 6

# Ação com efeito fora do notebook esperando o "sim" do usuário: (resposta, tarefa) ou None.
# Enviar mensagem no WhatsApp e editar um arquivo do Drive passam por aqui.
pending_action = None

CONFIRMATIONS = {"sim", "s", "pode", "pode enviar", "pode mandar", "envia", "manda", "confirmo", "ok"}


def reply_to(text, history):
    """Responde a uma mensagem do chat e executa a ação no próprio notebook.

    Retorna (resposta, tarefa). A tarefa é uma função sem argumentos que demora
    (Claude Code, Google, navegador) e deve rodar em segundo plano; ela devolve o texto
    para mostrar no chat. É None quando não há nada a esperar.
    """

    global pending_action

    if pending_action:
        reply, task = pending_action
        pending_action = None

        if normalize(text).strip(" .!") in CONFIRMATIONS:
            return reply, task

        # Qualquer outra resposta cancela; se for um pedido novo, ele segue normalmente.
        if normalize(text).strip(" .!") in {"nao", "n", "cancela", "cancelar"}:
            return "Certo, senhor. Cancelado.", None

    match = (
        detect_browser(text) or detect_command(text) or detect_contact(text) or detect_drive(text) or detect_google(text)
    )

    if match:
        return run_command(*match, text)

    try:
        answer, command = ask(text, history)

    except LLMError as error:
        print("ERRO NA IA:", repr(error))
        return "Desculpe, senhor. Minha inteligência está indisponível no momento.", None

    if not command:
        return answer, None

    if command.startswith((MEMORY_PREFIX, FORGET_PREFIX)):
        return continue_after_memory(run_command(command, answer, text)[0], text, history)

    return run_command(command, answer, text)


def ask(text, history, extra=None, tools=None):
    # Só os fatos da memória ligados à pergunta vão junto, para gastar poucos tokens.
    return ask_llm(
        text, "desktop", memory.context(text) + history[-HISTORY_LIMIT:] + (extra or []),
        tools or TOOLS + GOOGLE_TOOLS + BROWSER_TOOLS + ICLOUD_TOOLS + MEMORY_TOOLS
    )


def continue_after_memory(note, text, history):
    """Depois de guardar algo, segue a conversa: a mesma frase pode trazer outro pedido."""

    extra = [{
        "role": "system",
        "content": f"Você acabou de guardar na memória ({note}). Atenda agora o resto do pedido do usuário, "
                   "se houver. Se ele só pediu para lembrar algo, responda apenas OK."
    }]

    try:
        answer, command = ask(text, history, extra, TOOLS + GOOGLE_TOOLS + BROWSER_TOOLS + ICLOUD_TOOLS)

    except LLMError as error:
        print("ERRO NA IA:", repr(error))
        return note, None

    if command:
        reply, task = run_command(command, answer, text)
        return f"{note} {reply}".strip(), task

    if plain(answer) == "ok":
        return note, None

    return f"{note} {answer}", None


def run_command(command, answer, text):
    """Executa um comando do roteador ou da IA. Retorna (resposta, tarefa)."""

    global pending_action

    if command.startswith(CLAUDE_CODE_PREFIX):
        task = command[len(CLAUDE_CODE_PREFIX):]
        return answer, lambda: run_task(task)

    if command.startswith(MEMORY_PREFIX):
        return memory.remember(*memory_args(command)), None

    if command.startswith(FORGET_PREFIX):
        return memory.forget(*memory_args(command)), None

    if command.startswith(GOOGLE_AGENDA_PREFIX):
        days = int(command[len(GOOGLE_AGENDA_PREFIX):])
        return answer, lambda: agenda(days, text)

    if command.startswith(ICLOUD_CONTACT_PREFIX):
        name = memory.contact_name(command[len(ICLOUD_CONTACT_PREFIX):])
        return answer, lambda: run_icloud(icloud_data.contact_summary, name)

    if command == GOOGLE_CLASSROOM:
        return answer, lambda: run_google(google_data.classroom_summary, None, text)

    if command.startswith(WHATSAPP_PREFIX):
        contact, message = whatsapp_args(command)

        try:
            name, phone = whatsapp_app.recipient(memory.contact_name(contact))
            name = name or contact

        except Exception as error:
            return f"Desculpe, senhor. Não consegui achar o número: {error}", None

        pending_action = "Enviando, senhor.", lambda: run_whatsapp(phone, message)
        return f"Enviar \"{message}\" para {name} (+{phone}) no WhatsApp? Responda \"sim\" para confirmar.", None

    if command.startswith(DRIVE_PREFIX):
        action, name, value, new_value = drive_args(command)

        if action in DRIVE_READS:
            function = {"buscar": drive_data.search_summary, "ler": drive_data.read_summary, "baixar": drive_data.download}
            return answer, lambda: run_google(function[action], name, text)

        try:
            # O arquivo é escolhido agora, para a confirmação mostrar exatamente o que vai mudar.
            account, drive, docs, file = drive_data.find_one(name, drive_data.services(text))
            drive_data.check_edit(action, file)

        except Exception as error:
            return f"Desculpe, senhor. Não vou editar: {error}", None

        pending_action = "Editando, senhor.", lambda: drive_data.edit(action, drive, docs, file, value, new_value)
        return f"{drive_data.edit_question(action, file, value, new_value)} Responda \"sim\" para confirmar.", None

    if command == INSTAGRAM_MESSAGES:
        return answer, lambda: run_browser(browser.instagram_unread)

    if command == GOOGLE_YOUTUBE:
        return answer, lambda: with_pdf(text, "Relatorio YouTube", run_google(google_data.youtube_summary, text))

    try:
        run_action(command)

    except Exception as error:
        return f"Desculpe, senhor. Não consegui executar a ação: {error}", None

    return answer, None


def run_task(task):
    """Roda uma tarefa do Claude Code e devolve o texto para mostrar no chat."""

    status, result = call_claude_code(task)

    if status == "completed":
        return f"Claude Code terminou: {result}"

    return f"O Claude Code falhou: {result}"


def run_google(function, *args):
    try:
        return function(*args)

    except Exception as error:
        print("ERRO NO GOOGLE:", repr(error))
        return f"Desculpe, senhor. Não consegui consultar o Google: {error}"


def agenda(days, text):
    """Agenda do Google e, se o iCloud estiver configurado, o calendário do iPhone."""

    result = run_google(google_data.agenda_summary, days, None, text)

    if icloud_data.configured():
        result += "\n\n" + run_icloud(icloud_data.agenda_summary, days)

    return result


def run_icloud(function, *args):
    try:
        return function(*args)

    except Exception as error:
        print("ERRO NO ICLOUD:", repr(error))
        return f"Desculpe, senhor. Não consegui consultar o iCloud: {error}"


def run_whatsapp(phone, message):
    try:
        return whatsapp_app.send(phone, message)

    except Exception as error:
        print("ERRO NO WHATSAPP:", repr(error))
        return f"Desculpe, senhor. Não consegui usar o WhatsApp: {error}"


def run_browser(function, *args):
    try:
        return function(*args)

    except Exception as error:
        print("ERRO NO NAVEGADOR:", repr(error))
        return f"Desculpe, senhor. Não consegui usar o navegador: {error}"


def with_pdf(request, title, result):
    """Se o pedido falar em PDF ou relatório, salva o resultado em PDF e abre o arquivo."""

    text = normalize(request)

    if "pdf" not in text and "relatorio" not in text:
        return result

    try:
        path = reports.save_pdf(title, result)
        reports.open_file(path)

    except Exception as error:
        return f"{result}\n\nNão consegui gerar o PDF: {error}"

    return f"{result}\n\nRelatório salvo em {path}"
