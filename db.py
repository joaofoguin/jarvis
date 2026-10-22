import os
import psycopg


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
