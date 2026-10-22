-- Passo 2: guarda o resultado real de cada comando executado pelo agente.
-- Estados possíveis: pending, completed, failed, rejected.
ALTER TABLE agent_commands ADD COLUMN IF NOT EXISTS result TEXT;
