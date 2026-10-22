# JARVIS — Documentação do Projeto

> Documento de continuidade do projeto: arquitetura, configuração, processos implementados, testes realizados e próximos passos.
>
> **Importante:** este arquivo registra o estado conhecido do projeto até 21/10/2026. Como o código pode ter mudado desde as últimas conversas, confira os arquivos atuais do repositório antes de aplicar alterações.

## 1. Objetivo

O JARVIS é um assistente pessoal em português do Brasil, desenvolvido em Python, com integração entre Alexa, uma API hospedada na Vercel, DeepSeek (antes Gemini), um banco PostgreSQL na Neon e um agente local no Windows.

Objetivos futuros incluem controlar programas locais, abrir sites, automatizar tarefas no VS Code, criar e testar código e interagir com o WhatsApp Web. A execução local deve permanecer limitada a ações autorizadas, sem aceitar comandos arbitrários de terminal.

## 2. Ambiente de desenvolvimento

- **Sistema operacional:** Windows 11.
- **Linguagem principal:** Python.
- **Projeto local:** `C:\Users\joaop\Documents\Code\JARVIS`
- **Ambiente virtual:** `venv`
- **Terminal utilizado:** PowerShell.
- **Dependências principais:** FastAPI, Uvicorn, python-dotenv, psycopg (com binários) e requests.
- **Hospedagem da API:** Vercel.
- **Banco de dados:** Neon PostgreSQL.
- **Modelo de IA configurado:** DeepSeek (`deepseek-chat`, alterável pela variável `DEEPSEEK_MODEL`). O Gemini foi removido em 22/10/2026 por causa da cota gratuita (seção 12).
- **Assistente de voz:** Alexa, skill em português do Brasil.

Não armazene chaves de API, senhas, tokens ou strings de conexão neste documento nem no Git.

## 3. Arquitetura atual

```text
Alexa
  ↓
Endpoint /alexa na API FastAPI hospedada na Vercel
  ↓
Roteador local (router.py) → comandos conhecidos vão direto para a fila
  ↓
DeepSeek (llm.py, só para perguntas abertas; tokens registrados em ai_usage)
  ↓
Neon PostgreSQL — fila agent_commands
  ↓
JARVIS Agent executado no PC Windows
  ↓
Lista de ações autorizadas
  ↓
Programa ou site local
```

A API também possui um endpoint `/jarvis`, usado para enviar perguntas diretamente à API.

O agente local consulta a fila de comandos periodicamente. Quando encontra um comando reconhecido, executa a ação permitida e solicita à API que marque o comando como concluído.

## 4. Endereços e arquivos importantes

- **Alias estável da API:** `https://jarvis-one-opal-45.vercel.app`
- **Endpoint da Alexa:** `https://jarvis-one-opal-45.vercel.app/alexa`
- **Endpoint de status do agente:** `/agent/status`
- **Consulta de comandos pendentes:** `/agent/commands`
- **Conclusão de comando:** `/agent/commands/{command_id}/complete`
- **Criação de comando:** `/agent/command`
- **Código principal:** `main.py`
- **Agente local:** `agent/agent.py`
- **Configuração de dependências:** `requirements.txt`
- **Variáveis locais:** `.env` (não versionar)

Use o alias estável para testes, em vez de URLs temporárias específicas de um deployment.

## 5. Dependências

O `requirements.txt` conhecido contém:

```text
fastapi
uvicorn
python-dotenv
psycopg[binary]
requests
```

O `requests` é usado pela API (chamadas ao DeepSeek) e pelo agente local. Para rodar os testes, instale `requirements-dev.txt`.

Instalação/atualização das dependências no PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se o ambiente virtual ainda não existir:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 6. Variáveis de ambiente

O arquivo `.env` local precisa conter as variáveis necessárias ao processo executado no computador. Os nomes conhecidos são:

```dotenv
DEEPSEEK_API_KEY=COLOQUE_SUA_CHAVE_LOCAL
POSTGRES_URL=COLOQUE_SUA_STRING_DE_CONEXAO_NEON
```

Os valores acima são marcadores ilustrativos, não credenciais válidas. Substitua-os localmente pelos valores corretos e **nunca os cole em issues, commits ou mensagens públicas**.

A API hospedada na Vercel precisa ter as variáveis configuradas nas definições do projeto Vercel, nos ambientes de deployment relevantes. Alterar o `.env` local não atualiza automaticamente as variáveis de ambiente da Vercel.

O `.gitignore` conhecido inclui:

```gitignore
.env
venv/
__pycache__/
```

Confirme que `.env` está ignorado antes de fazer commit:

```powershell
git status --short
git check-ignore .env
```

Se uma chave já foi publicada no Git, removê-la do arquivo não invalida a chave: revogue-a e gere outra.

## 7. Banco de dados Neon

A tabela usada como fila de comandos é:

```sql
CREATE TABLE agent_commands (
    id BIGSERIAL PRIMARY KEY,
    command TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at TIMESTAMPTZ
);
```

### Funcionamento da fila

1. A API insere uma linha com o comando e status `pending`.
2. O agente consulta os comandos pendentes em ordem crescente de ID.
3. O agente executa comandos explicitamente reconhecidos.
4. Após executar, o agente chama o endpoint de conclusão.
5. A API atualiza o status para `completed` e registra `executed_at`.

A consulta conhecida para buscar comandos pendentes usa:

```sql
SELECT id, command, status, created_at
FROM agent_commands
WHERE status = 'pending'
ORDER BY id ASC;
```

A conclusão atualiza apenas registros que ainda estejam `pending`. Comandos não autorizados podem permanecer pendentes e reaparecer a cada consulta; recomenda-se implementar estados como `rejected` ou `failed` e evitar reprocessamento infinito.

## 8. API FastAPI

### Endpoints conhecidos

| Método | Rota | Finalidade |
|---|---|---|
| `GET` | `/` | Informa que a API está online e identifica o assistente/engine. |
| `POST` | `/jarvis` | Recebe uma pergunta direta e, no estado conhecido, usa o roteador local e, se não for um comando, chama o DeepSeek. |
| `POST` | `/alexa` | Recebe requisições da skill Alexa e devolve uma resposta no formato Alexa Skills Kit. |
| `GET` | `/agent/status` | Retorna o estado do agente segundo a API. |
| `POST` | `/agent/command` | Insere um comando na fila. |
| `GET` | `/agent/commands` | Retorna comandos pendentes. |
| `POST` | `/agent/commands/{command_id}/complete` | Marca um comando pendente como concluído. |

Os endpoints de agente foram implementados para integrar a fila Neon ao computador local. No estado documentado, eles não tinham autenticação própria. **Isso precisa ser corrigido antes de considerar a API segura para uso público:** adicionar um token compartilhado entre agente e API, validar as chamadas e limitar os dados retornados.

Não crie um endpoint que aceite e execute livremente texto como `cmd`, PowerShell ou shell. Prefira nomes de ações e parâmetros validados por uma lista permitida.

### Executar a API localmente

Com o ambiente virtual ativado e as variáveis locais configuradas:

```powershell
uvicorn main:app --reload
```

O endereço local padrão do Uvicorn é `http://127.0.0.1:8000`. A documentação interativa da FastAPI normalmente fica em `/docs`.

## 9. Agente local do Windows

Arquivo: `agent/agent.py`

O agente conhecido:
- Consulta `https://jarvis-one-opal-45.vercel.app/agent/commands`.
- Verifica a fila a cada 5 segundos.
- Reconhece `open_app:notepad` e `open_website:whatsapp`.
- Abre o Bloco de Notas usando `notepad.exe`.
- Abre o WhatsApp Web em uma nova janela/aba do navegador padrão por meio de `cmd /c start`.
- Marca o comando como concluído após iniciar a ação.
- Registra no terminal comandos recebidos, ações e erros.

Iniciar no PowerShell, a partir da raiz do projeto:

```powershell
.\venv\Scripts\Activate.ps1
python .\agent\agent.py
```

Para parar o agente, use `Ctrl+C`. Após alterar `agent.py`, pare e inicie novamente o processo para garantir que o código novo esteja em execução.

Exemplo de log esperado:

```text
================================
       JARVIS AGENT
================================
Status: ONLINE

Aguardando comandos...
```

Ao receber uma ação, o terminal deve mostrar uma linha `[COMANDO RECEBIDO]` e, quando aplicável, `[AÇÃO]` e `[COMANDO CONCLUÍDO]`.

O estado `online` informado por `/agent/status` não comprova por si só que o processo local esteja ativo; são verificações separadas.

## 10. Comandos já implementados

| Comando interno | Resultado esperado | Estado conhecido |
|---|---|---|
| `open_app:notepad` | Abre o Bloco de Notas no PC que executa o agente. | Testado com sucesso. |
| `open_website:whatsapp` | Abre `https://web.whatsapp.com` no navegador padrão. | O agente reconheceu o comando após ser reiniciado; a abertura do site foi prevista pelo código. |

Os comandos são strings internas da fila. A linguagem natural dita à Alexa não é, por si só, executada no Windows: a API precisa converter a solicitação em uma ação permitida e enfileirá-la.

## 11. Integração com Alexa

Configuração conhecida da skill:
- Nome: **JARVIS**.
- Idioma/localidade: português do Brasil (`pt-BR`).
- Nome de invocação: `jarvis`.
- Intent personalizado: `JarvisIntent`.
- Slot: `question`, do tipo `AMAZON.SearchQuery`.
- Endpoint HTTPS: `https://jarvis-one-opal-45.vercel.app/alexa`.

Exemplos de enunciados configurados:

```text
pergunte {question}
me diga {question}
responda {question}
quero saber {question}
gostaria de saber {question}
Jarvis me diga {question}
Jarvis responda {question}
quero perguntar {question}
```

Também foram tratados `LaunchRequest`, `AMAZON.HelpIntent`, `AMAZON.StopIntent` e `AMAZON.CancelIntent`.

### Fluxo testado

O fluxo completo foi comprovado em um teste anterior:

1. O usuário invocou o JARVIS pela Alexa.
2. Pediu para abrir o Bloco de Notas.
3. A API reconheceu a intenção via Gemini no fluxo anterior.
4. O comando foi inserido na fila Neon.
5. O agente local recebeu o comando e abriu o Bloco de Notas.
6. O agente marcou o comando como concluído.

Esse teste comprova a comunicação entre Alexa, API, banco e agente local para a ação testada.

## 12. Gemini: limite gratuito e falha atual conhecida

O código usa `google-genai` e, no estado documentado, chama:

```python
interaction = client.interactions.create(
    model="gemini-3.6-flash",
    system_instruction=system_instruction,
    input=request.question
)
```

Durante os testes, a API retornou HTTP `429` com a mensagem de cota gratuita excedida para `generate_content_free_tier_requests`, modelo `gemini-3.6-flash`, informando um limite de 20 requisições no erro observado.

**Diagnóstico:** essa mensagem indica que o projeto/API key atingiu a cota disponível para a métrica informada. Alterar o `.env` de conexão com o Neon ou fazer novo deployment na Vercel não aumenta nem reinicia essa cota. O limite exato pode variar conforme o projeto, modelo e política vigente.

A falha foi observada no endpoint `/jarvis`, na chamada `client.interactions.create(...)`. Enquanto essa chamada ocorrer antes de reconhecer comandos básicos, mesmo comandos simples poderão falhar quando a cota estiver esgotada.

### Decisão técnica

Priorizar um roteador local determinístico para comandos conhecidos e chamar o Gemini apenas para perguntas que realmente necessitem de IA:

```text
Pergunta
  ↓
Reconhecedor local de intenções
  ├── Bloco de Notas → open_app:notepad
  ├── WhatsApp Web → open_website:whatsapp
  └── Outra pergunta → Gemini (se disponível)
```

O próximo passo recomendado é implementar funções reutilizáveis como `detect_command(question)` e `enqueue_agent_command(command)`, e chamá-las antes do Gemini tanto no `/jarvis` quanto no `/alexa`. A detecção deve usar regras claras e específicas, sem confundir perguntas comuns com uma ordem para abrir um programa.

A resposta à Alexa deve ser natural, por exemplo, “Abrindo o Bloco de Notas, senhor.”, mas a ação interna deve continuar sendo um comando fixo autorizado. Deve existir um tratamento de erro para falhas do Gemini, para que a API não devolva um traceback completo ao usuário.

### Atualização de 22/10/2026: troca para DeepSeek

- O Gemini foi removido. Perguntas abertas usam o DeepSeek pela API compatível com OpenAI (`llm.py`), com limite de 300 tokens de saída e timeout de 7 segundos (a Alexa desiste após cerca de 8).
- O roteador determinístico (`router.py`) resolve Bloco de Notas e WhatsApp Web sem IA, em `/jarvis` e `/alexa`. O `/alexa` agora também enfileira o WhatsApp.
- Falhas do DeepSeek ou do Neon devolvem uma frase amigável, sem traceback.
- Cada chamada de IA registra tokens de entrada, de cache e de saída na tabela `ai_usage` (criar com `sql/ai_usage.sql`) e no log da Vercel (`[USO DE IA]`). Essa tabela é a base da análise de custos antes de contratar outras IAs.
- Na Vercel, configure `DEEPSEEK_API_KEY` e, se quiser, remova `GEMINI_API_KEY`.

## 13. Histórico de resultados e problemas

### Resultados confirmados
- A API foi implantada na Vercel e o alias estável `https://jarvis-one-opal-45.vercel.app` foi configurado.
- A skill Alexa foi construída com sucesso.
- A conexão da API com Neon foi testada.
- Comandos de teste foram inseridos e consultados na tabela `agent_commands`.
- O agente local abriu o Bloco de Notas a partir de um comando recebido pela fila.
- O fluxo Alexa → Vercel → Gemini → Neon → agente local → Windows funcionou para abrir o Bloco de Notas.
- O agente foi atualizado para reconhecer `open_website:whatsapp`; foi necessário reiniciá-lo depois da alteração.

### Problema atual conhecido
- A chamada ao Gemini retorna `429` quando a cota gratuita está esgotada.
- O `.env` local e o deploy não resolvem esse limite.
- A solução de arquitetura escolhida é tratar os comandos previsíveis sem Gemini e reservar chamadas de IA para solicitações abertas.

## 14. Próximos passos sugeridos

Recomenda-se implementar e validar uma etapa por vez:

1. **Roteador determinístico:** detectar pedidos de abrir Bloco de Notas e WhatsApp Web antes de chamar Gemini.
2. **Centralizar a fila:** criar uma única função para inserir comandos no Neon e reutilizá-la em `/jarvis` e `/alexa`.
3. **Tratamento de erros:** responder de forma controlada a falhas de conexão com Neon, indisponibilidade do Gemini e erros inesperados.
4. **Autenticação:** proteger rotas do agente com um segredo compartilhado armazenado em variáveis de ambiente; nunca embutir segredos no repositório.
5. **Estado de falha:** marcar comandos não autorizados ou falhos como `rejected`/`failed` e evitar que sejam repetidos indefinidamente.
6. **Resultados de execução:** permitir que o agente envie o resultado da ação para a API, em vez de registrar apenas que o processo foi iniciado.
7. **Abrir VS Code:** implementar uma ação explícita e autorizada, validando o caminho do workspace.
8. **Criar e testar arquivos:** limitar a criação a um diretório de trabalho permitido e executar somente tipos de testes previamente autorizados.
9. **Automação do WhatsApp Web:** avaliar Playwright localmente; confirmar o contato e a mensagem antes de enviar qualquer conteúdo.
10. **Testes automatizados:** testar o roteador e as funções da fila sem depender de chamadas reais ao Gemini.

Não implemente tudo de uma vez. Primeiro faça o roteador determinístico e valide os dois comandos existentes.

## 15. Segurança e manutenção

- Não versionar `.env`, chaves de API, senhas, tokens nem strings de conexão.
- Não executar texto arbitrário recebido da Alexa ou da API como comando de terminal.
- Usar uma lista de ações permitidas e validar todos os argumentos.
- Restringir criação e execução de arquivos a um workspace autorizado.
- Exigir confirmação explícita antes de ações com efeitos externos, como enviar mensagens.
- Proteger os endpoints da fila com autenticação.
- Evitar retornar tracebacks, credenciais ou detalhes internos ao usuário.
- Não assumir que um comando foi concluído só porque um processo foi iniciado; registrar o resultado real quando possível.
- Ao alterar o código do agente, reiniciar o processo local.
- Depois de validar localmente, fazer deploy e testar o alias estável.

## 16. Checklist para retomar o desenvolvimento

- [ ] Abrir `C:\Users\joaop\Documents\Code\JARVIS` no VS Code.
- [ ] Ativar o ambiente virtual.
- [ ] Confirmar que `.env` existe localmente e está ignorado pelo Git.
- [ ] Conferir se `DEEPSEEK_API_KEY` e `POSTGRES_URL` estão configuradas sem exibir seus valores.
- [ ] Revisar o `main.py` atual antes de substituir blocos de código.
- [ ] Implementar reconhecimento local de comandos antes da chamada ao Gemini.
- [ ] Testar localmente a abertura do Bloco de Notas e do WhatsApp Web.
- [ ] Reiniciar o agente local depois de qualquer alteração em `agent.py`.
- [ ] Confirmar que a fila marca os comandos executados como `completed`.
- [ ] Rodar `git status --short` e revisar o que será versionado.
- [ ] Fazer commit sem segredos.
- [ ] Fazer deploy somente depois de os testes locais passarem.

---

**Fim do documento.** Atualize esta documentação quando forem implementados novos comandos, controles de segurança ou mudanças de arquitetura. Verifique sempre o estado real do repositório antes de tratar qualquer item futuro como já concluído.
