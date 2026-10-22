from agent.agent import call_claude_code, run_action
from llm import LLMError, ask_llm
from router import CLAUDE_CODE_PREFIX, detect_command


# Mensagens anteriores enviadas à IA. Mais contexto custa mais tokens.
HISTORY_LIMIT = 6


def reply_to(text, history):
    """Responde a uma mensagem do chat e executa a ação no próprio notebook.

    Retorna (resposta, tarefa). A tarefa é o pedido para o Claude Code, que
    demora e deve rodar em segundo plano, ou None.
    """

    match = detect_command(text)

    if not match:
        try:
            answer, command = ask_llm(text, "desktop", history[-HISTORY_LIMIT:])

        except LLMError as error:
            print("ERRO NA IA:", repr(error))
            return "Desculpe, senhor. Minha inteligência está indisponível no momento.", None

        if not command:
            return answer, None

        match = command, answer

    command, answer = match

    if command.startswith(CLAUDE_CODE_PREFIX):
        return answer, command[len(CLAUDE_CODE_PREFIX):]

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
