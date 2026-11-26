import browser
import drive_data
import google_data
import icloud_data
import local_files
import memory
import reports
import whatsapp_app

from agent.agent import call_claude_code, run_action
from desktop import settings
from llm import BROWSER_TOOLS, FILE_TOOLS, GOOGLE_TOOLS, ICLOUD_TOOLS, MEMORY_TOOLS, TOOLS, LLMError, ask_llm
from router import (
    CLAUDE_CODE_PREFIX, DRIVE_PREFIX, DRIVE_READS, FORGET_PREFIX, GOOGLE_AGENDA_PREFIX, GOOGLE_CLASSROOM, GOOGLE_YOUTUBE,
    ICLOUD_CONTACT_PREFIX, INSTAGRAM_MESSAGES, LOCAL_FILE_PREFIX, MEMORY_PREFIX, WHATSAPP_PREFIX,
    detect_browser, detect_command, detect_contact, detect_drive, detect_google, drive_args, local_file_args, memory_args,
    normalize,
    plain, whatsapp_args
)


# Mensagens anteriores enviadas à IA. Mais contexto custa mais tokens.
HISTORY_LIMIT = 6

# Ação com efeito fora do notebook esperando o "sim" do usuário: (resposta, tarefa, comando) ou None.
# Enviar mensagem no WhatsApp e editar um arquivo do Drive passam por aqui.
pending_action = None

CONFIRMATIONS = {"sim", "s", "pode", "pode enviar", "pode mandar", "envia", "manda", "confirmo", "ok"}


# Rodadas da IA num pedido: ela usa uma ferramenta, vê o resultado e decide se falta outra.
MAX_STEPS = 4


def reply_to(text, history, record=None):
    """Responde a uma mensagem do chat e executa a ação no próprio notebook.

    Retorna (resposta, tarefa). A tarefa é uma função sem argumentos que demora
    (Claude Code, Google, navegador) e deve rodar em segundo plano; ela devolve o texto
    para mostrar no chat. É None quando não há nada a esperar.

    record recebe uma mensagem para o histórico a cada ação executada, para a IA saber
    depois o que foi feito (e conseguir "tentar de novo").
    """

    global pending_action

    record = record or (lambda message: None)

    if pending_action:
        reply, task, command = pending_action
        pending_action = None

        if normalize(text).strip(" .!") in CONFIRMATIONS:
            return reply, recorded(record, command, task)

        # Qualquer outra resposta cancela; se for um pedido novo, ele segue normalmente.
        if normalize(text).strip(" .!") in {"nao", "n", "cancela", "cancelar"}:
            return "Certo, senhor. Cancelado.", None

    match = (
        detect_browser(text) or detect_command(text) or detect_contact(text) or detect_drive(text) or detect_google(text)
    )

    if match:
        # Comando conhecido: roda sem IA e sem rodadas seguintes.
        command, answer = match
        reply, task = run_command(command, answer, text)

        if pending_action:
            return reply, None

        if task:
            return reply, recorded(record, command, task)

        record(executed(command))
        return reply, None

    try:
        answer, command = ask(text, history)

    except LLMError as error:
        print("ERRO NA IA:", repr(error))
        return "Desculpe, senhor. Minha inteligência está indisponível no momento.", None

    if not command:
        return answer, None

    return follow_steps(text, history, record, [], answer, command)


def ask(text, history, extra=None):
    # Só os fatos da memória ligados à pergunta vão junto, para gastar poucos tokens.
    return ask_llm(
        text, "desktop", memory.context(text) + history[-HISTORY_LIMIT:] + (extra or []),
        TOOLS + GOOGLE_TOOLS + BROWSER_TOOLS + ICLOUD_TOOLS + MEMORY_TOOLS + FILE_TOOLS
    )


def executed(command):
    return {"role": "system", "content": f"Ação executada: {command}"}


def recorded(record, command, task):
    """A tarefa registra a ação no histórico quando de fato roda."""

    def run():
        record(executed(command))
        return task()

    return run


def follow_steps(text, history, record, steps, answer, command, background=False):
    """Executa o comando da IA e mostra o resultado a ela, que pode pedir outra ação, até MAX_STEPS rodadas.

    steps: (comando, resultado) já executados neste pedido.
    Retorna (texto, tarefa). Quando uma ação demora, o texto até ali volta na hora e a tarefa
    continua o ciclo em segundo plano (background=True), onde as ações rodam direto.
    """

    shown = []

    while True:
        reply, task = run_command(command, answer, text)

        if pending_action:
            # Enviar mensagem e editar arquivo esperam o "sim"; o pedido para aqui.
            shown.append(reply)
            break

        if task and not background:
            return " ".join(filter(None, shown + [reply])), (
                lambda: follow_steps(text, history, record, steps, answer, command, background=True)[0]
            )

        record(executed(command))
        result = task() if task else reply
        shown.append(result)
        steps = steps + [(command, result)]

        if len(steps) >= MAX_STEPS:
            break

        try:
            answer, next_command = ask(text, history, [results_so_far(steps)])

        except LLMError as error:
            print("ERRO NA IA:", repr(error))
            break

        if not next_command:
            if plain(answer) != "ok":
                shown.append(answer)
            break

        # Repetir a mesma ação no mesmo pedido seria um ciclo sem fim. O Claude Code conta como a
        # mesma ação mesmo com outro texto: se falhou, tentar de novo sozinho só repete o erro.
        if action_kind(next_command) in {action_kind(done) for done, _ in steps}:
            break

        command = next_command

    return ("\n\n" if background else " ").join(filter(None, shown)), None


def action_kind(command):
    return CLAUDE_CODE_PREFIX if command.startswith(CLAUDE_CODE_PREFIX) else command


def results_so_far(steps):
    done = "\n".join(f"- {command}: {result}" for command, result in steps)

    return {
        "role": "system",
        "content": f"Para o pedido abaixo, você já executou estas ações, e o usuário já viu os resultados:\n{done}\n"
                   "Se o pedido ainda precisa de outra ação, use a ferramenta. "
                   "Se não falta nada, responda apenas OK, sem repetir os resultados."
    }


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
        return answer, lambda: run_google(classroom, text)

    if command.startswith(WHATSAPP_PREFIX):
        contact, message = whatsapp_args(command)

        try:
            name, phone = whatsapp_app.recipient(memory.contact_name(contact))
            name = name or contact

        except Exception as error:
            return f"Desculpe, senhor. Não consegui achar o número: {error}", None

        pending_action = "Enviando, senhor.", lambda: run_whatsapp(phone, message), command
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

        pending_action = "Editando, senhor.", lambda: drive_data.edit(action, drive, docs, file, value, new_value), command
        return f"{drive_data.edit_question(action, file, value, new_value)} Responda \"sim\" para confirmar.", None

    if command.startswith(LOCAL_FILE_PREFIX):
        action, name = local_file_args(command)

        try:
            path = local_files.find(name)

            if action == "abrir":
                return local_files.open_file(path), None

        except Exception as error:
            return f"Desculpe, senhor. Não consegui: {error}", None

        pending_action = "Apagando, senhor.", lambda: run_local(local_files.delete, path), command
        return f"Apagar {local_files.relative(path)}? Ele vai para a Lixeira. Responda \"sim\" para confirmar.", None

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


def classroom(text):
    """Sem citar uma conta no pedido, valem as contas do Classroom escolhidas nas preferências, como no painel."""

    mentioned = google_data.accounts(text) != google_data.accounts()
    only = None if mentioned else settings.load()["classroom_accounts"] or None
    return google_data.classroom_summary(google_data.services("classroom", "v1", text, only=only), text)


def run_google(function, *args):
    try:
        return function(*args)

    except Exception as error:
        print("ERRO NO GOOGLE:", repr(error))
        return f"Desculpe, senhor. Não consegui consultar o Google: {error}"


def agenda(days, text, account_services=None):
    """Agenda do Google e, se o iCloud estiver configurado, o calendário do iPhone."""

    result = run_google(google_data.agenda_summary, days, account_services, text)

    if icloud_data.configured():
        result += "\n\n" + run_icloud(icloud_data.agenda_summary, days)

    return result


def run_icloud(function, *args):
    try:
        return function(*args)

    except Exception as error:
        print("ERRO NO ICLOUD:", repr(error))
        return f"Desculpe, senhor. Não consegui consultar o iCloud: {error}"


def run_local(function, *args):
    try:
        return function(*args)

    except Exception as error:
        print("ERRO NO ARQUIVO:", repr(error))
        return f"Desculpe, senhor. Não consegui mexer no arquivo: {error}"


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
