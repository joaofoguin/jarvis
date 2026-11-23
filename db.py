import os
import psycopg


# "Hoje" no painel remoto começa à meia-noite daqui, não à meia-noite UTC do banco.
TIMEZONE = os.getenv("JARVIS_TIMEZONE", "America/Sao_Paulo")


def get_connection():
    database_url = os.getenv("POSTGRES_URL")

    if not database_url:
        raise RuntimeError("POSTGRES_URL não encontrada")

    return psycopg.connect(database_url)


def enqueue_agent_command(command):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_commands (command)
                VALUES (%s)
                RETURNING id
                """,
                (command,)
            )

            command_id = cur.fetchone()[0]
            conn.commit()

    return command_id


def list_pending_commands():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, command, status, created_at
                FROM agent_commands
                WHERE status = 'pending'
                ORDER BY id ASC
                """
            )

            return cur.fetchall()


def finish_agent_command(command_id, status, result):
    """Fecha um comando pendente; retorna None se ele não existir ou já tiver sido fechado."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_commands
                SET status = %s,
                    result = %s,
                    executed_at = NOW()
                WHERE id = %s
                  AND status = 'pending'
                RETURNING id, command, status
                """,
                (status, result, command_id)
            )

            row = cur.fetchone()
            conn.commit()

    return row


def save_chat_messages(conversation_id, messages):
    """Guarda as mensagens (role, content) de uma conversa do chat remoto."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chat_messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                [(conversation_id, role, content) for role, content in messages]
            )
            conn.commit()


def chat_history(conversation_id, limit):
    """Últimas mensagens da conversa, da mais antiga para a mais nova, no formato da IA."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content FROM chat_messages
                    WHERE conversation_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                ) recent
                ORDER BY id ASC
                """,
                (conversation_id, limit)
            )

            return [{"role": role, "content": content} for role, content in cur.fetchall()]


def telemetry():
    """Últimos comandos da fila e o uso de IA de hoje, para o painel remoto."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, command, status, result, created_at
                FROM agent_commands
                ORDER BY id DESC
                LIMIT 8
                """
            )
            commands = cur.fetchall()

            cur.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(prompt_tokens), 0), COALESCE(SUM(completion_tokens), 0)
                FROM ai_usage
                WHERE created_at >= date_trunc('day', NOW() AT TIME ZONE %s) AT TIME ZONE %s
                """,
                (TIMEZONE, TIMEZONE)
            )
            usage = cur.fetchone()

    return commands, usage
