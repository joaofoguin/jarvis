# CLAUDE.md

## Projeto JARVIS

- Assistente pessoal em português do Brasil: Alexa → API FastAPI (Vercel) → DeepSeek → fila no Neon → agente no Windows.
- Leia `JARVIS_DOCUMENTACAO.md` antes de mudar a arquitetura.
- Comandos conhecidos são resolvidos em `router.py`, sem IA. Só perguntas abertas vão para `llm.py`.
- Toda chamada de IA registra tokens na tabela `ai_usage` (`sql/ai_usage.sql`). Mantenha esse registro em qualquer novo provedor.
- As rotas da fila exigem `AGENT_TOKEN`. O agente fecha cada comando como `completed`, `failed` ou `rejected`.
- Ações que a IA pode escolher ficam em `TOOLS` (`llm.py`) e viram comandos por `command_for_tool` (`router.py`). Tarefas `claude_code:` rodam só dentro de `JARVIS_WORKSPACE`, sem Bash.
- A janela de chat (`desktop/`) reusa `router.py`, `llm.py` e as ações de `agent/agent.py`. Não duplique essa lógica.
- Google (Agenda, Classroom, mural do Classroom e YouTube) é só leitura e só no notebook (`google_data.py`, `desktop/notices.py`). Telas automáticas nunca abrem o login do Google sozinhas. Nunca versione `credentials.json` nem `google_token*.json`.
- O Google Drive (`drive_data.py`, login próprio "drive") busca, lê, baixa e edita só quando o usuário pede. As edições são fixas (acrescentar e substituir texto em Documentos Google, renomear) e sempre pedem um "sim" antes, como o WhatsApp.
- Contatos e calendário do iPhone vêm do iCloud (`icloud_data.py`), só leitura e só no notebook, com senha de app em `ICLOUD_APP_PASSWORD`.
- WhatsApp (app do Windows, `whatsapp_app.py`) e Instagram (navegador, `browser.py`) rodam só no notebook, como ações fixas. Enviar mensagem sempre pede um "sim" antes, e o Enter só vai para a janela do WhatsApp.
- A voz (`desktop/voice.py`) detecta "Hey Jarvis" no notebook e só depois manda o áudio para o reconhecimento. As preferências ficam em `~/.jarvis/preferencias.json` (`desktop/settings.py`).
- O painel de preferências (`desktop/panel.py`) só adiciona repositórios de Skills do GitHub validados, clonados sem terminal, e nunca substitui uma skill que já existe.
- O que o usuário ensina fica em `memory.py` (arquivos em `~/.jarvis/memoria`). Só os fatos ligados à pergunta vão para a IA; não mande a memória inteira.
- O agente local só executa ações de uma lista permitida. Nunca execute texto livre como comando de terminal.
- Nunca versione `.env`, chaves ou strings de conexão.
- Testes: `pip install -r requirements-dev.txt` e `python -m pytest`. Não chame APIs reais nos testes.

---

Diretrizes de comportamento abaixo adaptadas de [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills).

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
