import os
import psycopg

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from google import genai


# ============================================================
# CONFIGURAÇÃO
# ============================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no arquivo .env"
    )


client = genai.Client(api_key=api_key)

app = FastAPI(title="JARVIS")


# ============================================================
# MODELO DA REQUISIÇÃO
# ============================================================

class JarvisRequest(BaseModel):
    question: str


# ============================================================
# ROTA PRINCIPAL
# ============================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "assistant": "JARVIS",
        "engine": "Gemini 3.6 Flash"
    }


# ============================================================
# JARVIS
# ============================================================

@app.post("/jarvis")
def jarvis(request: JarvisRequest):

    system_instruction = """
    Você é JARVIS, um assistente pessoal inteligente.

    Você deve responder sempre em português do Brasil.

    PERSONALIDADE:
    - Educado
    - Inteligente
    - Objetivo
    - Sofisticado
    - Levemente formal
    - Pode chamar o usuário de "senhor" quando apropriado.

    VOZ:
    - Suas respostas serão faladas pela Alexa.
    - Não use Markdown.
    - Não use emojis.
    - Seja natural e relativamente conciso.

    COMANDOS DO COMPUTADOR:

    Quando o usuário pedir para abrir o Bloco de Notas,
    responda EXATAMENTE:

    open_app:notepad

    Quando o usuário pedir para abrir o WhatsApp Web,
    responda EXATAMENTE:

    open_website:whatsapp

    Não adicione nenhuma outra palavra.
    Não explique.
    Não use pontuação.

    Por enquanto, essas são as únicas ações de computador disponíveis.
    """

    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        system_instruction=system_instruction,
        input=request.question
    )

    answer = interaction.output_text.strip()

    if answer == "open_app:notepad":
        database_url = os.getenv("POSTGRES_URL")

        if not database_url:
            raise RuntimeError("POSTGRES_URL não encontrada")

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_commands (command)
                    VALUES (%s)
                    """,
                    ("open_app:notepad",)
                )
                conn.commit()

        return {
            "answer": "Abrindo o Bloco de Notas, senhor."
        }


    if answer == "open_website:whatsapp":
        database_url = os.getenv("POSTGRES_URL")

        if not database_url:
            raise RuntimeError("POSTGRES_URL não encontrada")

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_commands (command)
                    VALUES (%s)
                    """,
                    ("open_website:whatsapp",)
                )
                conn.commit()

        return {
            "answer": "Abrindo o WhatsApp Web, senhor."
        }


    return {
        "answer": answer
    }

@app.post("/alexa")
def alexa(request: dict):

    try:
        # ========================================================
        # IDENTIFICAR O TIPO DE REQUISIÇÃO
        # ========================================================

        request_type = request.get("request", {}).get("type")

        # ========================================================
        # LAUNCH REQUEST
        # ========================================================

        if request_type == "LaunchRequest":

            return {
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Olá, senhor. JARVIS online. Como posso ajudá-lo?"
                    },
                    "shouldEndSession": False
                }
            }

        # ========================================================
        # INTENT REQUEST
        # ========================================================

        if request_type == "IntentRequest":

            intent = request.get("request", {}).get("intent", {})
            intent_name = intent.get("name")

            # ----------------------------------------------------
            # PARAR / CANCELAR
            # ----------------------------------------------------

            if intent_name in [
                "AMAZON.StopIntent",
                "AMAZON.CancelIntent"
            ]:

                return {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": "Até logo, senhor."
                        },
                        "shouldEndSession": True
                    }
                }

            # ----------------------------------------------------
            # AJUDA
            # ----------------------------------------------------

            if intent_name == "AMAZON.HelpIntent":

                return {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": "Pode me fazer uma pergunta e eu tentarei ajudá-lo."
                        },
                        "shouldEndSession": False
                    }
                }

            # ----------------------------------------------------
            # JARVIS
            # ----------------------------------------------------

            if intent_name == "JarvisIntent":

                slots = intent.get("slots", {})
                question_slot = slots.get("question", {})

                question = question_slot.get("value")

                if not question:

                    return {
                        "version": "1.0",
                        "response": {
                            "outputSpeech": {
                                "type": "PlainText",
                                "text": "Desculpe, senhor. Não consegui entender sua pergunta."
                            },
                            "shouldEndSession": False
                        }
                    }

                # ------------------------------------------------
                # GEMINI
                # ------------------------------------------------

                system_instruction = """
                Você é JARVIS, um assistente pessoal inteligente.

                PERSONALIDADE:
                - Educado
                - Inteligente
                - Objetivo
                - Sofisticado
                - Levemente formal
                - Pode chamar o usuário de "senhor" quando apropriado.

                IDIOMA:
                - Responda sempre em português do Brasil.

                VOZ:
                - Sua resposta será falada pela Alexa.
                - Não use Markdown.
                - Não use emojis.
                - Não use listas muito longas.
                - Seja natural.
                - Seja relativamente conciso.

                COMANDOS DO COMPUTADOR:

                Quando o usuário pedir para abrir o Bloco de Notas,
                responda EXATAMENTE:

                open_app:notepad

                Quando o usuário pedir para abrir o WhatsApp Web,
                responda EXATAMENTE:

                open_website:whatsapp

                Não adicione nenhuma outra palavra.
                Não explique.
                Não use pontuação.

                Por enquanto, essas são as únicas ações de computador disponíveis.
                """

                interaction = client.interactions.create(
                    model="gemini-3.6-flash",
                    system_instruction=system_instruction,
                    input=question
                )

                answer = interaction.output_text.strip()

                if answer == "open_app:notepad":
                    database_url = os.getenv("POSTGRES_URL")

                    if not database_url:
                        raise RuntimeError("POSTGRES_URL não encontrada")

                    with psycopg.connect(database_url) as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO agent_commands (command)
                                VALUES (%s)
                                """,
                                ("open_app:notepad",)
                            )

                            conn.commit()

                    answer = "Abrindo o Bloco de Notas, senhor."
                # ------------------------------------------------
                # RESPOSTA PARA ALEXA
                # ------------------------------------------------

                return {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": answer
                        },
                        "shouldEndSession": True
                    }
                }

        # ========================================================
        # TIPO DESCONHECIDO
        # ========================================================

        return {
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "Desculpe, senhor. Não consegui processar essa solicitação."
                },
                "shouldEndSession": True
            }
        }

    except Exception as e:

        print("ERRO NO JARVIS:", repr(e))

        return {
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "Desculpe, senhor. Ocorreu um problema ao processar sua solicitação."
                },
                "shouldEndSession": True
            }
        }

@app.get("/agent/status")
def agent_status():
    return {
        "status": "online",
        "agent": "JARVIS Agent"
    }

class AgentCommand(BaseModel):
    command: str


@app.post("/agent/command")
def create_agent_command(request: AgentCommand):
    database_url = os.getenv("POSTGRES_URL")

    if not database_url:
        raise RuntimeError("POSTGRES_URL não encontrada")

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_commands (command)
                VALUES (%s)
                RETURNING id, command, status
                """,
                (request.command,)
            )

            result = cur.fetchone()
            conn.commit()

    return {
        "id": result[0],
        "command": result[1],
        "status": result[2]
    }

@app.get("/agent/commands")
def get_agent_commands():
    database_url = os.getenv("POSTGRES_URL")

    if not database_url:
        raise RuntimeError("POSTGRES_URL não encontrada")

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, command, status, created_at
                FROM agent_commands
                WHERE status = 'pending'
                ORDER BY id ASC
                """
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "command": row[1],
            "status": row[2],
            "created_at": row[3].isoformat()
        }
        for row in rows
    ]

@app.post("/agent/commands/{command_id}/complete")
def complete_agent_command(command_id: int):
    database_url = os.getenv("POSTGRES_URL")

    if not database_url:
        raise RuntimeError("POSTGRES_URL não encontrada")

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_commands
                SET status = 'completed',
                    executed_at = NOW()
                WHERE id = %s
                  AND status = 'pending'
                RETURNING id, command, status
                """,
                (command_id,)
            )

            result = cur.fetchone()
            conn.commit()

    if not result:
        return {
            "success": False,
            "message": "Comando não encontrado ou já concluído"
        }

    return {
        "success": True,
        "id": result[0],
        "command": result[1],
        "status": result[2]
    }