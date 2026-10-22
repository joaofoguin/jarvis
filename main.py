import os
import secrets
import psycopg

from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from db import enqueue_agent_command, finish_agent_command, list_pending_commands
from llm import DEEPSEEK_MODEL, LLMError, ask_llm
from router import ALLOWED_COMMANDS, detect_command


# ============================================================
# CONFIGURAÇÃO
# ============================================================

load_dotenv()

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
        "engine": f"DeepSeek ({DEEPSEEK_MODEL})"
    }


# ============================================================
# PROCESSAMENTO DE PERGUNTAS
# ============================================================

def handle_question(question, source):
    """Comandos conhecidos vão direto para a fila; o resto vai para a IA."""

    match = detect_command(question)

    if match:
        command, answer = match

        try:
            enqueue_agent_command(command)

        except (psycopg.Error, RuntimeError) as error:
            print("ERRO AO ENFILEIRAR COMANDO:", repr(error))
            return "Desculpe, senhor. Não consegui enviar o comando ao computador."

        return answer

    try:
        return ask_llm(question, source)

    except LLMError as error:
        print("ERRO NA IA:", repr(error))
        return "Desculpe, senhor. Minha inteligência está indisponível no momento."


# ============================================================
# JARVIS
# ============================================================

@app.post("/jarvis")
def jarvis(request: JarvisRequest):

    return {
        "answer": handle_question(request.question, "jarvis")
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

                answer = handle_question(question, "alexa")

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


# ============================================================
# FILA DO AGENTE (protegida por token)
# ============================================================

def require_agent_token(authorization: str = Header(default="")):
    expected = os.getenv("AGENT_TOKEN")

    # Sem token configurado, a fila fica fechada em vez de aberta para todos.
    if not expected:
        raise HTTPException(status_code=503, detail="AGENT_TOKEN não configurado")

    if not secrets.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Token inválido")


class AgentCommand(BaseModel):
    command: str


class CommandResult(BaseModel):
    status: Literal["completed", "failed", "rejected"] = "completed"
    result: str | None = None


@app.post("/agent/command", dependencies=[Depends(require_agent_token)])
def create_agent_command(request: AgentCommand):

    if request.command not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail="Comando não permitido")

    command_id = enqueue_agent_command(request.command)

    return {
        "id": command_id,
        "command": request.command,
        "status": "pending"
    }


@app.get("/agent/commands", dependencies=[Depends(require_agent_token)])
def get_agent_commands():

    return [
        {
            "id": row[0],
            "command": row[1],
            "status": row[2],
            "created_at": row[3].isoformat()
        }
        for row in list_pending_commands()
    ]


@app.post("/agent/commands/{command_id}/complete", dependencies=[Depends(require_agent_token)])
def complete_agent_command(command_id: int, request: CommandResult | None = None):

    request = request or CommandResult()

    # Limita o texto salvo para que um erro enorme não encha o banco.
    result = request.result[:500] if request.result else None

    row = finish_agent_command(command_id, request.status, result)

    if not row:
        return {
            "success": False,
            "message": "Comando não encontrado ou já finalizado"
        }

    return {
        "success": True,
        "id": row[0],
        "command": row[1],
        "status": row[2]
    }
