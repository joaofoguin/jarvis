-- Núcleo VPS do JARVIS. Não altera agent_commands nem as demais tabelas legadas.
CREATE TABLE IF NOT EXISTS jarvis_conversations (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(160) NOT NULL DEFAULT 'Nova conversa',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS jarvis_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL REFERENCES jarvis_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT,
    tool_calls JSONB,
    tool_call_id VARCHAR(128),
    name VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_jarvis_messages_conversation_id ON jarvis_messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_jarvis_messages_conversation_created ON jarvis_messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS jarvis_tasks (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_jarvis_tasks_status ON jarvis_tasks(status);

-- Mantém compatibilidade com o registro de tokens já usado pelo JARVIS.
CREATE TABLE IF NOT EXISTS ai_usage (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    source TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
