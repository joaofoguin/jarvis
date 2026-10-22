import google_data

from agent.agent import call_claude_code, run_action
from llm import GOOGLE_TOOLS, TOOLS, LLMError, ask_llm
from router import CLAUDE_CODE_PREFIX, GOOGLE_AGENDA_PREFIX, GOOGLE_CLASSROOM, detect_command, detect_google


# Mensagens anteriores enviadas à IA. Mais contexto custa mais tokens.
HISTORY_LIMIT = 6


def reply_to(text, history):
    """Responde a uma mensagem do chat e executa a ação no próprio notebook.

    Retorna (resposta, tarefa). A tarefa é uma função sem argumentos que demora
    (Claude Code, Google) e deve rodar em segundo plano; ela devolve o texto
    para mostrar no chat. É None quando não há nada a esperar.
    """

    match = detect_command(text) or detect_google(text)

    if not match:
        try:
            answer, command = ask_llm(text, "desktop", history[-HISTORY_LIMIT:], TOOLS + GOOGLE_TOOLS)

        except LLMError as error:
            print("ERRO NA IA:", repr(error))
            return "Desculpe, senhor. Minha inteligência está indisponível no momento.", None

        if not command:
            return answer, None

        match = command, answer

    command, answer = match

    if command.startswith(CLAUDE_CODE_PREFIX):
        task = command[len(CLAUDE_CODE_PREFIX):]
        return answer, lambda: run_task(task)

    if command.startswith(GOOGLE_AGENDA_PREFIX):
        days = int(command[len(GOOGLE_AGENDA_PREFIX):])
        return answer, lambda: run_google(google_data.agenda_summary, days, None, text)

    if command == GOOGLE_CLASSROOM:
        return answer, lambda: run_google(google_data.classroom_summary, None, text)

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
