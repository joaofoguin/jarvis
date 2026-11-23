import httpx
from server.config import Settings

class DeepSeekError(RuntimeError):
    pass

SYSTEM_PROMPT = """Você é JARVIS, um assistente pessoal inteligente.
Responda sempre em português brasileiro, com educação, clareza e objetividade.
Seu tom é sofisticado, discreto e levemente formal. Pode chamar o usuário de senhor quando natural.
Você pode utilizar ferramentas disponibilizadas pelo sistema. Só diga que uma ação foi realizada
depois de receber e verificar o resultado da ferramenta. Nunca invente acesso a contas, arquivos
ou dispositivos. Para ações externas ou destrutivas, aguarde a implementação de autorização
específica; não tente contornar essa limitação. Se uma ferramenta não estiver disponível, explique
com transparência e ofereça uma alternativa segura."""

class DeepSeekClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        if not self.settings.deepseek_api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY não configurada.")
        url = self.settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            "tools": tools,
            "tool_choice": "auto",
            "thinking": {"type": "disabled"},
            "temperature": 0.4,
            "max_tokens": 1600,
        }
        headers = {"Authorization": "Bearer " + self.settings.deepseek_api_key}
        try:
            async with httpx.AsyncClient(timeout=self.settings.deepseek_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as error:
            raise DeepSeekError("A API DeepSeek retornou HTTP " + str(error.response.status_code) + ".") from error
        except (httpx.HTTPError, ValueError) as error:
            raise DeepSeekError("Não foi possível consultar a API DeepSeek.") from error
