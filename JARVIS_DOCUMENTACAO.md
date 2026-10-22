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
AGENT_TOKEN=COLOQUE_UM_TOKEN_ALEATORIO
JARVIS_WORKSPACE=C:\Users\joaop\Documents\Code\jarvis-workspace
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
    executed_at TIMESTAMPTZ,
    result TEXT  -- adicionada no passo 2 (sql/agent_commands_result.sql)
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

A conclusão atualiza apenas registros que ainda estejam `pending`. O agente fecha cada comando com um destes estados: `completed` (ação executada), `failed` (a ação deu erro) ou `rejected` (comando fora da lista permitida). A coluna `result` guarda a descrição do resultado. Assim nenhum comando fica reaparecendo na fila.

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

As rotas `/agent/command`, `/agent/commands` e `/agent/commands/{command_id}/complete` exigem o cabeçalho `Authorization: Bearer <AGENT_TOKEN>`. O mesmo token fica no `.env` do PC e nas variáveis da Vercel. Sem `AGENT_TOKEN` configurado no servidor, essas rotas respondem 503 (a fila fica fechada). `/agent/command` só aceita comandos da lista permitida (`is_allowed_command` em `router.py`). `/agent/status` continua público.

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
- Envia o `AGENT_TOKEN` do `.env` em todas as chamadas.
- Fecha cada comando como `completed`, `failed` ou `rejected`, com a descrição do resultado.
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
| `claude_code:<tarefa>` | Roda o Claude Code na pasta `JARVIS_WORKSPACE`, só lendo e editando arquivos, e devolve um resumo. | Implementado no passo 3; ainda não testado no PC. |

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

### Atualização de 22/10/2026: fila protegida (passo 2)

- Rotas da fila exigem `AGENT_TOKEN` (ver seção 8).
- Novos estados `failed` e `rejected` e coluna `result` (rodar `sql/agent_commands_result.sql` no Neon).
- Gere o token no PowerShell com `python -c "import secrets; print(secrets.token_urlsafe(32))"` e coloque o mesmo valor no `.env` e na Vercel.
- API e agente precisam ser atualizados juntos: o agente antigo não envia token e passa a receber 401.

### Atualização de 22/10/2026: a IA escolhe as ações (passo 3)

- O DeepSeek recebe as ações como ferramentas (function calling): `open_notepad`, `open_whatsapp` e `claude_code`. Quando a IA escolhe uma, a API enfileira o comando correspondente da lista permitida. Assim frases como "preciso anotar uma coisa" também abrem o Bloco de Notas.
- O roteador local continua primeiro, sem gastar tokens. Ele também reconhece "peça ao Claude para ...", "manda pro Claude Code pra ..." e frases parecidas.
- Novo comando `claude_code:<tarefa>` (até 1000 caracteres). O agente roda `claude -p` em segundo plano, dentro da pasta `JARVIS_WORKSPACE`, com o login da assinatura do Claude, e devolve um resumo como resultado do comando.
- O Claude Code só pode ler e editar arquivos (`Read`, `Edit`, `Write`, `Glob`, `Grep`), e o Bash fica bloqueado. Ele não executa programas nem testes. Liberar a execução de testes é uma decisão futura.
- Limite de 10 minutos por tarefa. Se o agente for reiniciado no meio de uma tarefa, ela roda de novo, porque continua `pending`.
- Requisitos no PC: Claude Code instalado e logado (`claude` no PowerShell), e a pasta de `JARVIS_WORKSPACE` criada.

### Atualização de 22/10/2026: janela de chat no notebook

- `desktop/app.py` é um app que fica em segundo plano, com um ícone perto do relógio do Windows. O atalho `Ctrl+Alt+J` mostra e esconde a janela, e o atalho pode ser trocado pela variável `JARVIS_HOTKEY`. `Esc` esconde a janela.
- O app não passa pela Vercel nem pela fila. Ele usa o mesmo roteador e o mesmo DeepSeek (`desktop/core.py`) e executa as ações direto no notebook, com as funções do agente.
- O DeepSeek recebe as últimas 6 mensagens da conversa como contexto. Os tokens são registrados com a origem `desktop`.
- Tarefas do Claude Code rodam em segundo plano, e o resultado aparece no chat quando terminam.
- Para instalar, rode `pip install -r requirements-desktop.txt`. Para abrir, rode `pythonw -m desktop.app` na raiz do projeto.

### Atualização de 22/10/2026: Google Agenda e Classroom no chat

- `google_data.py` lê a Google Agenda (calendário principal) e as atividades pendentes do Classroom. O acesso é somente leitura, com os escopos `calendar.readonly`, `classroom.courses.readonly` e `classroom.coursework.me.readonly`.
- Só funciona na janela de chat do notebook. A Vercel e a Alexa não têm o login do Google.
- O roteador (`detect_google`) reconhece frases como "o que tenho hoje", "agenda da semana" e "tarefas pendentes" sem gastar tokens. A IA também pode escolher as ferramentas `ver_agenda` e `ver_tarefas_classroom`.
- O resultado aparece direto no chat, sem uma segunda chamada à IA, e fica no histórico para perguntas seguintes.
- Configuração: `credentials.json` (cliente OAuth do tipo "App para computador", criado no Google Cloud) fica na raiz do projeto. No primeiro uso, o navegador abre para o login, e o token fica salvo em `google_token.json`. Esses arquivos estão no `.gitignore`.
- Várias contas: defina `GOOGLE_ACCOUNTS=email1,email2` no `.env`. Cada conta faz login uma vez (o navegador já abre com o e-mail sugerido) e ganha seu próprio `google_token_<email>.json`. A agenda e o Classroom juntam as contas e marcam cada linha com o e-mail. Se uma conta falhar, as outras continuam aparecendo. Se o pedido citar parte de um e-mail ("conta discente", "uenp"), só essa conta é consultada.

### Atualização de 22/10/2026: métricas do YouTube e relatório em PDF

- `google_data.youtube_summary` lê o canal (inscritos e visualizações), os 5 vídeos mais recentes e, do último vídeo, as métricas do YouTube Analytics (tempo assistido, duração média, porcentagem assistida, inscritos ganhos e compartilhamentos). O acesso é somente leitura, com `youtube.readonly` e `yt-analytics.readonly`.
- O YouTube tem um login separado, só na conta do canal, salvo em `google_token_<email>_youtube.json`. A conta vem do pedido ou de `YOUTUBE_ACCOUNT` no `.env`.
- O roteador reconhece "youtube", "insights" e "métricas do meu vídeo/canal" sem gastar tokens. A IA também pode escolher a ferramenta `ver_youtube`.
- Se o pedido citar "PDF" ou "relatório", `reports.py` (fpdf2) salva o resultado em PDF na pasta `JARVIS_WORKSPACE` (ou em Documentos) e abre o arquivo. O PDF é gerado pelo próprio JARVIS, sem IA e sem terminal.
- No Google Cloud, é preciso ativar a **YouTube Data API v3** e a **YouTube Analytics API** no projeto.

### Atualização de 22/10/2026: WhatsApp e Instagram pelo navegador

- `browser.py` controla o Edge com o Playwright, usando um perfil só do JARVIS (`~/.jarvis/navegador`, ou `JARVIS_BROWSER_PROFILE`). O login no WhatsApp Web (QR code) e no Instagram é feito uma vez nesse navegador e fica salvo no perfil, fora do Git.
- São ações fixas, não navegação livre: `whatsapp_enviar` (procura o contato pelo nome exato e envia o texto) e `instagram_mensagens` (lista quem mandou mensagens novas e quantas, pela mesma chamada que o site do Instagram faz).
- Antes de enviar uma mensagem, o JARVIS pergunta "Enviar ... para ...?" e só envia depois de um "sim". Qualquer outra resposta cancela.
- Apelidos vêm da memória do JARVIS ("lembre que minha namorada é a Amor"). O antigo `WHATSAPP_APELIDOS` no `.env` continua valendo.
- O roteador (`detect_browser`) reconhece "manda mensagem para X no WhatsApp dizendo Y" e "mensagens novas no Instagram" sem gastar tokens. A IA também pode escolher `enviar_whatsapp` e `ver_mensagens_instagram`.
- Só funciona na janela de chat do notebook. Os sites mudam com frequência; se uma ação parar de funcionar, os seletores em `browser.py` precisam de ajuste.

### Atualização de 22/10/2026: contatos e calendário do iPhone (iCloud)

- `icloud_data.py` lê os contatos (CardDAV, `contacts.icloud.com`) e o calendário (CalDAV, `caldav.icloud.com`, com a biblioteca `caldav`) do iCloud. É somente leitura e só funciona na janela de chat do notebook.
- O login usa `ICLOUD_EMAIL` e `ICLOUD_APP_PASSWORD` no `.env`. A senha é uma senha de app criada em account.apple.com, nunca a senha da conta Apple.
- "Qual o número da X?" é reconhecido sem IA (`detect_contact`), e a IA também pode usar `buscar_contato`. Os apelidos da memória do JARVIS valem aqui, então "minha namorada" vira "Amor".
- Quando o iCloud está configurado, os pedidos de agenda mostram o calendário do iCloud logo abaixo da agenda do Google.
- O resultado fica no histórico do chat, e o histórico vai para a IA na próxima pergunta aberta. Então telefones consultados podem chegar à DeepSeek.

### Atualização de 22/10/2026: memória do JARVIS

- `memory.py` guarda o que o usuário ensina no chat em arquivos Markdown, um por assunto, em `~/.jarvis/memoria` (ou `JARVIS_MEMORY`), fora do Git: `apelidos.md` e `fatos.md`. Os arquivos podem ser abertos e editados à mão.
- "lembre que / aprenda que / anote que ..." guarda, e "esqueça que ..." apaga. O roteador reconhece essas frases sem IA (`detect_memory`), e a IA também pode usar a ferramenta `lembrar`.
- Frases como "minha namorada é a Amor" viram apelidos, usados para achar contatos no iCloud e no WhatsApp. `WHATSAPP_APELIDOS` no `.env` continua funcionando, mas não é mais necessário.
- A cada pergunta aberta, só os fatos que têm palavras em comum com a pergunta (no máximo 5) vão para a IA. Os outros ficam no arquivo e não gastam tokens.
- Nomes de contatos são comparados sem emojis e acentos (`router.plain`), e a busca parcial só aceita palavras inteiras.

### Atualização de 22/10/2026: WhatsApp pelo aplicativo do Windows

- O envio pelo WhatsApp saiu do navegador e agora usa o aplicativo do Windows (`whatsapp_app.py`). O `browser.py` ficou só com o Instagram.
- O número vem da memória (apelido) e dos contatos do iCloud (`whatsapp_app.recipient`). Também dá para ditar o número direto. Se houver mais de um contato com o nome, o JARVIS pede o nome completo.
- A confirmação mostra o nome e o número: `Enviar "..." para Amor (+55...)?`. Só depois do "sim" o JARVIS abre `whatsapp://send?phone=...&text=...` e aperta Enter.
- O Enter só é apertado se a janela da frente for o WhatsApp, para nunca ir para outro programa. Se o app não ficar na frente em 15 segundos, a conversa fica aberta com o texto pronto, sem envio.
- Números sem "+" e com DDD (10 ou 11 dígitos) ganham o código 55 do Brasil.

### Atualização de 22/10/2026: memória com assunto, chave e valor

- A memória deixou de usar regras de frases específicas ("meu X é Y", "eu sou", "lembre que"). Agora a IA decide o que guardar e chama `lembrar(assunto, chave, valor)` ou `esquecer(assunto, chave)`.
- Os assuntos são fixos: `usuario`, `contatos`, `preferencias` e `geral`. Cada um tem um arquivo (`usuario.md` etc.) com linhas `- chave: valor`. Os antigos `apelidos.md` e `fatos.md` não são mais lidos.
- Guardar a mesma chave de novo substitui o valor. Pedir para reformular ou repetir uma informação não cria cópias.
- `contatos` liga o jeito como o usuário chama alguém (chave) a um nome dos contatos ou a um número (valor). O WhatsApp e a busca de contatos usam isso.
- Todo o assunto `usuario` vai sempre para a IA. Dos outros assuntos, só vão os itens com palavras em comum com a pergunta, no máximo 5.
- Quando a IA guarda ou apaga algo, o JARVIS faz uma segunda chamada, sem as ferramentas de memória, para atender o resto da frase. Se não houver mais nada, a IA responde "OK", e o chat mostra só a confirmação.
- O prompt pede que a IA use sempre `enviar_whatsapp` para enviar ou mudar uma mensagem, em vez de pedir confirmação em texto.

### Atualização de 22/10/2026: conversa por voz

- `desktop/voice.py` fica ouvindo "Hey Jarvis" pelo microfone. A palavra é detectada no próprio notebook com o openWakeWord; nenhum áudio sai do notebook antes dela.
- Depois do "Hey Jarvis", a frase vai para o reconhecimento de voz do Google em português e segue pelo mesmo `reply_to` do chat. A resposta aparece na janela e é lida por uma voz neural da Microsoft (edge-tts).
- Depois de responder, o JARVIS espera alguns segundos por outra frase sem precisar de "Hey Jarvis", para dar para conversar. Se você ficar em silêncio, ele volta a esperar a palavra de ativação.
- O item "Falar agora" no menu do ícone faz o JARVIS ouvir sem a palavra de ativação.
- As preferências ficam em `~/.jarvis/preferencias.json` (`desktop/settings.py`): voz, velocidade, ouvir "Hey Jarvis" e responder falando. O painel de preferências vai editar esse arquivo.
- Sem microfone ou sem internet, o chat por texto continua funcionando.
- Para instalar, rode `pip install -r requirements-desktop.txt`. Na primeira vez, o modelo do "Hey Jarvis" é baixado sozinho.

### Atualização de 22/10/2026: orbe flutuante e chat novo

- A janela de tkinter foi trocada por duas telas web dentro do Python (pywebview, que usa o WebView2 já instalado no Windows). As telas ficam em `desktop/web/`.
- `orb.html` é o orbe: pequeno, redondo, sem borda e sempre por cima, no canto inferior direito. Ele respira em espera, solta ondas quando ouve, gira quando pensa e mostra barras em volta quando fala. Dá para arrastar.
- Clique no orbe para falar. Com o botão direito, o chat abre e fecha.
- `chat.html` é o chat no mesmo visual. Tem botão de microfone, e `Esc` esconde a janela. Fechar a janela só a esconde; para sair, use o ícone perto do relógio.
- A cor vem de `accent` em `~/.jarvis/preferencias.json` (padrão `#3FD4F5`).
- O Python fala com as telas por `evaluate_js`, com textos passados por `json.dumps`, e as mensagens entram como texto, nunca como HTML.

### Atualização de 22/10/2026: painel de preferências

- O painel (`desktop/web/panel.html` e `desktop/panel.py`) abre pelo ícone perto do relógio ("Preferências") ou pela engrenagem do chat. As mudanças valem na hora, sem reiniciar.
- **Uso de IA:** mostra os tokens dos últimos 14 dias, lidos de `ai_usage` (`desktop/usage.py`), com o total por dia e por origem e o custo estimado. O custo usa o preço de pico do deepseek-flash conferido em 22/10/2026; se o preço mudar, atualize as constantes em `desktop/usage.py`. Sem `POSTGRES_URL`, só essa parte fica vazia.
- **Aparência e voz:** cor do orbe, voz neural, velocidade da fala e um botão para testar a voz.
- **Reconhecimento:** liga e desliga o "Hey Jarvis" automático e as respostas faladas.
- **Repositórios de Skills** (`desktop/skills.py`): aceita só `https://github.com/dono/repositorio`. O repositório é baixado com `git clone` em `~/.jarvis/skills`, e cada pasta com `SKILL.md` é copiada para `JARVIS_WORKSPACE/.claude/skills`, onde o Claude Code a encontra. Uma skill que já existe nunca é substituída. Remover apaga só o que veio daquele repositório.
- **Memória:** lista os itens de cada assunto e permite apagar um item.
- As preferências são validadas antes de gravar (voz da lista, velocidade de -50% a +50%, cor em `#RRGGBB`).

### Atualização de 22/10/2026: tela cheia, notícias e janelas sem barra

- O orbe tira o fundo cinza que o Windows pintava atrás da janela transparente (`clear_background` em `desktop/app.py`, com uma cor-chave quase preta).
- O chat e o painel não têm mais a barra do Windows. Cada um tem os próprios botões (preferências, tela cheia, esconder) e é arrastado pelo topo.
- Em tela cheia (ou com a janela larga), o chat fica à esquerda e um painel do dia aparece à direita (`desktop/dashboard.py`). Ele mostra hora e data, agenda de hoje (Google e iCloud), tarefas do Classroom, notícias, histórico dos últimos pedidos e o uso de IA de hoje. Cada parte carrega sozinha e se atualiza a cada 10 minutos.
- O painel do dia só consulta o Google se o login já foi feito, para nunca abrir o navegador sozinho.
- As notícias vêm do RSS público do Google Notícias, sem chave, nos temas de `news_topics`. Os temas são editados em Preferências > Notícias, com até 10 temas. Clicar numa notícia abre o navegador padrão; só links `https://` são abertos.
- O histórico fica em `~/.jarvis/historico.jsonl` (o pedido e o começo da resposta), fora do Git.

### Atualização de 22/10/2026: orbe redondo, Classroom filtrado e avisos do mural

- A transparência do WebView2 deixava um quadrado cinza, e a cor-chave (`TransparencyKey`) fazia a janela parar de receber cliques. Agora a janela do orbe é recortada num círculo (`SetWindowRgn`, em `make_round`), com fundo escuro e um aro fino, e os cliques voltam a funcionar.
- O Classroom do painel em tela cheia mostra só as atividades pendentes criadas nos últimos 30 dias (`classroom_summary(..., since=...)`), nas contas marcadas em Preferências > Classroom (`classroom_accounts`; sem nenhuma marcada, valem todas).
- **Avisos do mural** (`desktop/notices.py`):
  - Pedem um login a mais, só de leitura (`classroom.announcements.readonly`, token `_mural`), feito pelo botão "Conectar avisos do mural" nas preferências.
  - A cada 5 minutos o app consulta os avisos das contas escolhidas.
  - Cada aviso novo vira uma notificação do Windows e uma mensagem no chat.
  - Na primeira consulta de uma turma, os avisos que já existiam só são marcados como vistos (em `~/.jarvis/avisos_vistos.json`), sem notificar.
- As notícias aparecem em blocos, como no Iniciar do Windows 10: o primeiro grande, alguns largos e cada tema com um tom da cor escolhida.

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
