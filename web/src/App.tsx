import { FormEvent, useEffect, useRef, useState } from "react";

type ChatMessage = { role: "user" | "assistant"; content: string };
type ChatResult = { conversation_id: string; answer: string; model: string; prompt_tokens: number; completion_tokens: number };
type Task = { id: number; title: string; description: string; status: string };

const API_URL = (import.meta.env.VITE_JARVIS_API_URL || "").replace(/\/$/, "");

export default function App() {
  const [token, setToken] = useState("");
  const [tokenDraft, setTokenDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "assistant", content: "Boa noite, senhor. JARVIS online. Como posso ajudá-lo?" }]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, busy]);

  async function loadTasks(activeToken: string) {
    if (!API_URL) return;
    try {
      const response = await fetch(API_URL + "/api/v1/tasks", { headers: { Authorization: "Bearer " + activeToken } });
      if (!response.ok) throw new Error("Não foi possível carregar as tarefas.");
      setTasks(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao consultar tarefas.");
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    if (!API_URL) { setError("Configure VITE_JARVIS_API_URL no ambiente da interface web."); return; }
    if (!token) { setShowSettings(true); setError("Informe o token de acesso para conectar ao JARVIS."); return; }

    setInput("");
    setError("");
    setMessages((current) => [...current, { role: "user", content: text }]);
    setBusy(true);
    try {
      const response = await fetch(API_URL + "/api/v1/chat", {
        method: "POST",
        headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, conversation_id: conversationId, source: "mobile" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "O servidor não conseguiu processar a solicitação.");
      const result = data as ChatResult;
      setConversationId(result.conversation_id);
      setMessages((current) => [...current, { role: "assistant", content: result.answer }]);
      await loadTasks(token);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha de comunicação com o JARVIS.");
    } finally {
      setBusy(false);
    }
  }

  function startNewConversation() {
    setConversationId(null);
    setMessages([{ role: "assistant", content: "Nova conversa iniciada. À disposição, senhor." }]);
    setError("");
  }

  function connect(event: FormEvent) {
    event.preventDefault();
    setToken(tokenDraft.trim());
    setShowSettings(false);
    setError("");
    if (tokenDraft.trim()) void loadTasks(tokenDraft.trim());
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><div className="brand-orb"><span /></div><div><strong>JARVIS</strong><small>PERSONAL INTELLIGENCE</small></div></div>
        <div className="top-actions"><span className={token ? "connection online" : "connection"}>{token ? "CONECTADO" : "OFFLINE"}</span><button className="icon-button" onClick={() => setShowSettings((value) => !value)} aria-label="Configurações">⚙</button></div>
      </header>

      {showSettings && (
        <form className="settings-panel" onSubmit={connect}>
          <label htmlFor="token">Token de acesso do JARVIS</label>
          <input id="token" type="password" autoComplete="off" value={tokenDraft} onChange={(event) => setTokenDraft(event.target.value)} placeholder="Cole seu JARVIS_API_TOKEN" />
          <p>O token fica somente na memória desta aba e não é salvo no navegador.</p>
          <div className="settings-actions"><button type="button" className="secondary" onClick={() => { setToken(""); setTokenDraft(""); setTasks([]); }}>Desconectar</button><button type="submit" className="primary">Conectar</button></div>
        </form>
      )}

      <section className="workspace">
        <section className="chat-panel">
          <div className="section-heading"><div><span className="eyebrow">ASSISTENTE PESSOAL</span><h1>À disposição, senhor.</h1></div><button className="secondary compact" onClick={startNewConversation}>Nova conversa</button></div>
          <div className="messages">
            {messages.map((message, index) => <article className={"message " + message.role} key={index}><span className="message-author">{message.role === "user" ? "VOCÊ" : "JARVIS"}</span><p>{message.content}</p></article>)}
            {busy && <div className="typing"><i /><i /><i /><span>JARVIS está processando</span></div>}
            <div ref={bottomRef} />
          </div>
          {error && <div className="error" role="alert">{error}</div>}
          <form className="composer" onSubmit={sendMessage}>
            <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Diga ao JARVIS o que precisa..." rows={2} disabled={busy} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
            <button className="send-button" type="submit" disabled={busy || !input.trim()} aria-label="Enviar mensagem">↑</button>
          </form>
          <div className="composer-hint">ENTER PARA ENVIAR · SHIFT + ENTER PARA QUEBRAR LINHA</div>
        </section>
        <aside className="side-panel">
          <div className="side-card"><span className="eyebrow">SISTEMA</span><div className="status-row"><span>API</span><b>{API_URL ? "CONFIGURADA" : "PENDENTE"}</b></div><div className="status-row"><span>Sessão</span><b>{token ? "AUTENTICADA" : "NÃO CONECTADA"}</b></div></div>
          <div className="side-card"><div className="side-title"><span className="eyebrow">TAREFAS</span><span className="count">{tasks.length}</span></div>
            {tasks.length ? tasks.map((task) => <div className="task" key={task.id}><span className="task-dot" /><div><strong>{task.title}</strong>{task.description && <small>{task.description}</small>}</div></div>) : <p className="muted">Suas tarefas registradas aparecerão aqui.</p>}
            {token && <button className="refresh" onClick={() => void loadTasks(token)}>Atualizar tarefas</button>}
          </div>
          <div className="side-note">O painel remoto depende da VPS e do computador conectado para executar operações locais.</div>
        </aside>
      </section>
      <footer>JARVIS · ACESSO REMOTO SEGURO · {new Date().getFullYear()}</footer>
    </main>
  );
}
