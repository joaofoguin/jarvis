# JARVIS na VPS e no celular

A API é uma só: `main.py`. Ela roda na Vercel ou numa VPS com Docker, e as duas usam o mesmo Neon, o mesmo roteador (`router.py`), a mesma IA (`llm.py`) e a mesma fila do agente.

Além da Alexa e da fila, a API serve a página **`/app`**: um chat no estilo HUD que funciona no navegador e no celular (dá para instalar na tela inicial). Ela fala com `/api/chat` e mostra a fila do agente e o uso de IA do dia (`/api/telemetry`).

## O que a página faz

- Comandos conhecidos vão direto para a fila, sem IA, como na Alexa.
- Perguntas abertas vão para o DeepSeek com as 6 últimas mensagens da conversa, guardadas na tabela `chat_messages`.
- Cada chamada de IA é registrada em `ai_usage`.
- As ações rodam no notebook pelo agente. Google, iCloud, WhatsApp, Instagram e memória continuam só na janela do notebook.

## Preparar o banco (uma vez)

No SQL Editor do Neon, rode `sql/chat_messages.sql`. As outras tabelas já existem.

## Variáveis

| Variável | Para quê |
|---|---|
| `JARVIS_API_TOKEN` | Senha da página `/app`. Gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Sem ela, `/api/chat` fica fechado. |
| `POSTGRES_URL`, `DEEPSEEK_API_KEY`, `AGENT_TOKEN` | As mesmas de sempre. |

Na Vercel, adicione `JARVIS_API_TOKEN` em Settings → Environment Variables e rode `vercel --prod`. A página fica em `https://SEU-PROJETO.vercel.app/app/`.

## Rodar numa VPS (opcional)

1. Instale Docker e Docker Compose e clone o repositório.
2. `cp .env.vps.example .env.vps` e preencha.
3. Aponte o domínio para o IP da VPS (`JARVIS_DOMAIN`).
4. `docker compose -f docker-compose.vps.yml --profile tls up -d --build`.
5. No `.env` do notebook, ponha `JARVIS_URL=https://SEU-DOMINIO` para o agente buscar a fila na VPS.

A porta 8000 fica só em localhost; o acesso de fora passa pelo Caddy, com HTTPS.

## Testes

```powershell
pip install -r requirements-dev.txt
python -m pytest
```
