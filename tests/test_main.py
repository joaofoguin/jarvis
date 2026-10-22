import pytest
from fastapi.testclient import TestClient

import main
from llm import LLMError


@pytest.fixture
def client(monkeypatch):
    queued = []
    monkeypatch.setattr(main, "enqueue_agent_command", queued.append)
    monkeypatch.setattr(main, "ask_llm", lambda question, source: (f"IA: {question}", None))
    test_client = TestClient(main.app)
    test_client.queued = queued
    return test_client


def alexa_body(question):
    return {
        "request": {
            "type": "IntentRequest",
            "intent": {
                "name": "JarvisIntent",
                "slots": {"question": {"value": question}}
            }
        }
    }


def test_known_command_skips_ai(client):
    response = client.post("/jarvis", json={"question": "abra o bloco de notas"})

    assert response.json() == {"answer": "Abrindo o Bloco de Notas, senhor."}
    assert client.queued == ["open_app:notepad"]


def test_alexa_whatsapp_is_queued(client):
    response = client.post("/alexa", json=alexa_body("abre o whatsapp"))

    assert response.json()["response"]["outputSpeech"]["text"] == "Abrindo o WhatsApp Web, senhor."
    assert client.queued == ["open_website:whatsapp"]


def test_other_questions_go_to_ai(client):
    response = client.post("/jarvis", json={"question": "que horas são em Tóquio"})

    assert response.json() == {"answer": "IA: que horas são em Tóquio"}
    assert client.queued == []


def test_ai_failure_gives_friendly_answer(client, monkeypatch):
    def fail(question, source):
        raise LLMError("cota esgotada")

    monkeypatch.setattr(main, "ask_llm", fail)

    response = client.post("/alexa", json=alexa_body("conte uma piada"))

    assert response.json()["response"]["outputSpeech"]["text"] == (
        "Desculpe, senhor. Minha inteligência está indisponível no momento."
    )


def test_queue_failure_gives_friendly_answer(client, monkeypatch):
    def fail(command):
        raise RuntimeError("POSTGRES_URL não encontrada")

    monkeypatch.setattr(main, "enqueue_agent_command", fail)

    response = client.post("/jarvis", json={"question": "abra o bloco de notas"})

    assert response.json() == {
        "answer": "Desculpe, senhor. Não consegui enviar o comando ao computador."
    }


def test_action_chosen_by_ai_is_queued(client, monkeypatch):
    monkeypatch.setattr(main, "ask_llm", lambda question, source: ("Certo, senhor.", "claude_code:criar hello.py"))

    response = client.post("/jarvis", json={"question": "cria um hello world"})

    assert response.json() == {"answer": "Certo, senhor."}
    assert client.queued == ["claude_code:criar hello.py"]
