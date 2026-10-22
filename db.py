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
