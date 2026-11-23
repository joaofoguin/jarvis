# JARVIS — núcleo VPS (v2)

Esta evolução adiciona um backend preparado para VPS sem remover o backend legado, o desktop PySide6/orbe ou as integrações atuais.

## O que funciona nesta primeira entrega

- API FastAPI separada do ponto de entrada legado `main.py`.
- Cliente DeepSeek com Function Calling.
- Persistência de conversas e mensagens em PostgreSQL.
- Ferramentas internas para criar e listar tarefas.
- Registro de consumo de tokens na tabela `ai_usage`.
- Autenticação Bearer nos endpoints privados.
- Health checks e configuração Docker.
- HTTPS opcional com Caddy.

O núcleo ainda **não** controla o Windows, não envia WhatsApp e não acessa contas Google/Apple/Microsoft. Essas ações serão conectadas por módulos e agentes autenticados nas próximas etapas.

## Compatibilidade

- `main.py`, `llm.py`, `router.py`, `agent/` e `desktop/` continuam preservados.
- Novo ponto de entrada: `vps_main.py` ou `server.main:app`.
- A configuração aceita `DATABASE_URL`; também pode ser preenchida com a antiga `POSTGRES_URL`.
- As tabelas novas usam prefixo `jarvis_`; não alteram a fila legada.

## Rodar localmente no Windows

No PowerShell, na raiz do repositório:

```powershell
py -3.12 -m venv .venv-vps
.\.venv-vps\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-vps-dev.txt
Copy-Item .env.vps.example .env.vps
```

Edite `.env.vps` e informe `DEEPSEEK_API_KEY`, `DATABASE_URL` (pode ser a URL Neon já usada) e `JARVIS_API_TOKEN`. Gere o token com:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Para desenvolvimento, use `AUTO_CREATE_SCHEMA=true`. Inicie:

```powershell
uvicorn vps_main:app --reload --host 127.0.0.1 --port 8000
```

Verifique `GET /health/live` e `GET /health/ready` em `http://127.0.0.1:8000`.

Exemplo de conversa:

```powershell
$headers = @{ Authorization = "Bearer SEU_JARVIS_API_TOKEN" }
$body = @{ message = "Jarvis, registre uma tarefa para revisar redes de computadores."; source = "desktop" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/chat -Headers $headers -ContentType "application/json" -Body $body
```

A resposta inclui `conversation_id`. Envie esse identificador na próxima solicitação para continuar a conversa.

## Banco de dados

Antes de usar PostgreSQL de produção, faça backup e revise `sql/vps_core.sql`. Execute o script no banco escolhido e mantenha `AUTO_CREATE_SCHEMA=false`. Não execute migrações em produção sem backup.

## Deploy na VPS

1. Instale Docker Engine e Docker Compose.
2. Clone o repositório e selecione a branch de evolução.
3. Copie `.env.vps.example` para `.env.vps` e preencha os segredos.
4. Aponte um domínio para o IP da VPS e configure `JARVIS_DOMAIN`.
5. Execute `sql/vps_core.sql` no PostgreSQL.
6. Inicie o app: `docker compose -f docker-compose.vps.yml up -d --build app`.
7. Para HTTPS automático: `docker compose -f docker-compose.vps.yml --profile tls up -d`.

A porta 8000 fica vinculada somente a localhost. Não exponha a API diretamente na internet sem HTTPS e autenticação.

## Voz local — próxima integração

`requirements-voice-local.txt` separa as dependências planejadas:
- faster-whisper: reconhecimento de fala local;
- Piper: síntese de voz local;
- sounddevice: captura e reprodução;
- openWakeWord: palavra de ativação.

A implementação atual de `desktop/voice.py` ainda usa reconhecimento Google e edge-tts. Ela não foi substituída nesta etapa para preservar a experiência existente. A migração para STT/TTS local será feita com testes próprios, sem enviar áudio a serviços externos.

## Testes

```powershell
pip install -r requirements-vps-dev.txt
python -m pytest tests/test_vps_core.py -q
```
