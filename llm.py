import json
import os
import requests

from db import get_connection
from router import COMMANDS, command_for_tool


DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# A Alexa desiste da resposta após cerca de 8 segundos.
TIMEOUT_SECONDS = 7

# Respostas faladas devem ser curtas; o limite também controla o custo.
MAX_TOKENS = 300

# Prompt fixo: o DeepSeek reaproveita prefixos repetidos (cache), que custam menos.
SYSTEM_PROMPT = """Você é JARVIS, um assistente pessoal inteligente.

PERSONALIDADE: educado, inteligente, objetivo, sofisticado e levemente formal.
Pode chamar o usuário de "senhor" quando apropriado.

IDIOMA: responda sempre em português do Brasil.

VOZ: sua resposta será falada pela Alexa. Não use Markdown, emojis nem listas longas.
Seja natural e conciso.

AÇÕES: quando o usuário pedir algo no computador dele, use a ferramenta correspondente.
Use claude_code só para pedidos de programação, como criar ou alterar código.

MENSAGENS: para enviar ou mudar uma mensagem de WhatsApp, use sempre enviar_whatsapp com o texto final
já escrito. O sistema pede a confirmação ao usuário; não peça confirmação em texto.

MEMÓRIA: use lembrar só quando o usuário ensinar algo novo ou pedir para lembrar."""


def tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or []
            }
        }
    }


# Ações que a IA pode escolher; cada uma vira um comando da lista permitida.
TOOLS = [tool(item["tool"], item["description"]) for item in COMMANDS] + [
    tool(
        "claude_code",
        "Pede ao Claude Code, no computador do usuário, para criar ou alterar código "
        "na pasta de trabalho do JARVIS.",
        {"task": {"type": "string", "description": "A tarefa de programação, completa e em português."}},
        ["task"]
    )
]


# Só a janela de chat do notebook oferece estas, porque o login do Google fica nele.
GOOGLE_TOOLS = [
    tool(
        "ver_agenda",
        "Lista os compromissos da Google Agenda do usuário a partir de hoje.",
        {"dias": {"type": "integer", "description": "Quantos dias olhar, de 1 (só hoje) a 7."}},
        ["dias"]
    ),
    tool(
        "ver_tarefas_classroom",
        "Lista as atividades pendentes do usuário no Google Classroom."
    ),
    tool(
        "ver_youtube",
        "Mostra as métricas do canal do YouTube do usuário e dos vídeos mais recentes "
        "(visualizações, curtidas, tempo assistido, retenção, inscritos ganhos)."
    )
]


# Também só no notebook: usam o navegador do JARVIS, com o login do usuário.
BROWSER_TOOLS = [
    tool(
        "enviar_whatsapp",
        "Envia uma mensagem no WhatsApp Web para um contato. O usuário confirma antes do envio.",
        {
            "contato": {"type": "string", "description": "O contato como o usuário disse, por exemplo \"Amor\" ou \"minha namorada\"."},
            "mensagem": {
                "type": "string",
                "description": "O texto final, pronto para chegar ao contato. Se o usuário pedir para você "
                               "escrever (\"mande saudações suas\"), escreva como JARVIS, em nome do usuário."
            }
        },
        ["contato", "mensagem"]
    ),
    tool(
        "ver_mensagens_instagram",
        "Verifica as mensagens novas no Instagram: quem mandou e quantas."
    )
]


# Também só no notebook: os contatos do iPhone vêm do iCloud.
ICLOUD_TOOLS = [
    tool(
        "buscar_contato",
        "Procura um contato do iPhone do usuário pelo nome e mostra os telefones.",
        {"nome": {"type": "string", "description": "O nome do contato, como o usuário disse."}},
        ["nome"]
    )
]


# Também só no notebook: a memória fica em arquivos no computador do usuário.
MEMORY_TOOLS = [
    tool(
        "lembrar",
        "Guarda na memória algo novo que o usuário ensinou, como \"eu sou o Foguinho\". "
        "Se for um apelido de contato (\"toninho é o Toninho Hajime\"), preencha apelido e contato.",
        {
            "fato": {"type": "string", "description": "O que lembrar, numa frase curta."},
            "apelido": {"type": "string", "description": "Só para contatos: como o usuário chama a pessoa."},
            "contato": {"type": "string", "description": "Só para contatos: o nome salvo nos contatos."}
        },
        ["fato"]
    )
]


class LLMError(Exception):
    pass


def ask_llm(question, source, history=None, tools=None):
    """Retorna (resposta falada, comando). O comando é None quando a IA só respondeu.

    history: mensagens anteriores da conversa, no formato {"role", "content"}.
    tools: ferramentas oferecidas à IA; o padrão é TOOLS.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise LLMError("DEEPSEEK_API_KEY não encontrada")

    try:
        response = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *(history or []),
                    {"role": "user", "content": question}
                ],
                "tools": tools or TOOLS,
                "max_tokens": MAX_TOKENS
            },
            timeout=TIMEOUT_SECONDS
        )

        response.raise_for_status()

        data = response.json()
        message = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []

        if tool_calls:
            function = tool_calls[0]["function"]
            action = command_for_tool(function["name"], json.loads(function.get("arguments") or "{}"))
        else:
            action = None

        answer = (message.get("content") or "").strip()

    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
        raise LLMError(f"Falha ao consultar o DeepSeek: {error!r}") from error

    log_usage(source, data.get("model", DEEPSEEK_MODEL), data.get("usage") or {})

    if action:
        command, spoken = action
        return spoken, command

    if not answer:
        raise LLMError("O DeepSeek não devolveu texto nem uma ação válida")

    return answer, None


def log_usage(source, model, usage):
    """Registra os tokens de cada chamada para a análise de custos. Nunca derruba a resposta."""

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cache_hit_tokens = usage.get("prompt_cache_hit_tokens", 0)

    print(
        f"[USO DE IA] origem={source} modelo={model} "
        f"entrada={prompt_tokens} (cache={cache_hit_tokens}) saida={completion_tokens}"
    )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_usage
                        (provider, model, source, prompt_tokens,
                         cache_hit_tokens, completion_tokens)
                    VALUES ('deepseek', %s, %s, %s, %s, %s)
                    """,
                    (model, source, prompt_tokens, cache_hit_tokens, completion_tokens)
                )
                conn.commit()

    except Exception as error:
        print("ERRO AO REGISTRAR USO DE IA:", repr(error))
