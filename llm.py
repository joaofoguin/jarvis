import os
import requests

from db import get_connection


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
Seja natural e conciso."""


class LLMError(Exception):
    pass


def ask_llm(question, source):
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
                    {"role": "user", "content": question}
                ],
                "max_tokens": MAX_TOKENS
            },
            timeout=TIMEOUT_SECONDS
        )

        response.raise_for_status()

        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()

    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
        raise LLMError(f"Falha ao consultar o DeepSeek: {error!r}") from error

    log_usage(source, data.get("model", DEEPSEEK_MODEL), data.get("usage") or {})

    return answer


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
