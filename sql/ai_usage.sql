-- Registro de tokens por chamada de IA, usado na análise de custos.
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

-- Exemplo de consulta: tokens gastos por dia.
-- SELECT date_trunc('day', created_at) AS dia,
--        SUM(prompt_tokens) AS entrada,
--        SUM(cache_hit_tokens) AS entrada_em_cache,
--        SUM(completion_tokens) AS saida,
--        COUNT(*) AS chamadas
-- FROM ai_usage
-- GROUP BY 1
-- ORDER BY 1 DESC;
