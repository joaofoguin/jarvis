import datetime
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

import main


TOKEN = "segredo-do-chat"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    test_client = TestClient(main.app)
    test_client.saved = []
    test_client.asked = []
    test_client.queued = []

    def ask(question, source, history=None):
        test_client.asked.append((question, source, history))
        return f"IA: {question}", None

    monkeypatch.setattr(main, "ask_llm", ask)
    monkeypatch.setattr(main, "enqueue_agent_command", test_client.queued.append)
    monkeypatch.setattr(main, "chat_history", lambda conversation_id, limit: [
        {"role": "user", "content": "oi"}, {"role": "assistant", "content": "Olá, senhor."}
    ])
    monkeypatch.setattr(main, "save_chat_messages", lambda conversation_id, messages: test_client.saved.append(
        (conversation_id, messages)
    ))
    return test_client


def test_chat_needs_token(client):
    assert client.post("/api/chat", json={"message": "oi"}).status_code == 401


def test_chat_closed_without_token_configured(client, monkeypatch):
    monkeypatch.delenv("JARVIS_API_TOKEN")

    assert client.post("/api/chat", json={"message": "oi"}, headers=AUTH).status_code == 503


def test_new_conversation_skips_history_and_saves_both_messages(client):
    response = client.post("/api/chat", json={"message": "que horas são em Tóquio"}, headers=AUTH)
    data = response.json()

    assert data["answer"] == "IA: que horas são em Tóquio"
    assert client.asked == [("que horas são em Tóquio", "web", [])]
    assert client.saved == [(data["conversation_id"], [("user", "que horas são em Tóquio"), ("assistant", data["answer"])])]


def test_conversation_sends_history_to_ai(client):
    conversation = str(uuid.uuid4())

    response = client.post("/api/chat", json={"message": "e amanhã?", "conversation_id": conversation}, headers=AUTH)

    assert response.json()["conversation_id"] == conversation
    assert client.asked[0][2] == [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "Olá, senhor."}]


def test_known_command_goes_to_queue_without_ai(client):
    response = client.post("/api/chat", json={"message": "abra o bloco de notas"}, headers=AUTH)

    assert response.json()["answer"] == "Abrindo o Bloco de Notas, senhor."
    assert client.queued == ["open_app:notepad"]
    assert client.asked == []


def test_chat_still_answers_when_database_fails(client, monkeypatch):
    def fail(*args):
        raise psycopg.OperationalError("sem conexão")

    monkeypatch.setattr(main, "chat_history", fail)
    monkeypatch.setattr(main, "save_chat_messages", fail)

    response = client.post("/api/chat", json={"message": "oi", "conversation_id": str(uuid.uuid4())}, headers=AUTH)

    assert response.status_code == 200
    assert response.json()["answer"] == "IA: oi"


def test_invalid_conversation_id_is_rejected(client):
    assert client.post("/api/chat", json={"message": "oi", "conversation_id": "1; DROP"}, headers=AUTH).status_code == 422


def test_telemetry(client, monkeypatch):
    monkeypatch.setattr(main, "telemetry", lambda: (
        [(9, "open_app:notepad", "completed", "ok", datetime.datetime(2026, 11, 23, 20, 0))],
        (3, 1200, 90)
    ))

    data = client.get("/api/telemetry", headers=AUTH).json()

    assert data["commands"][0]["status"] == "completed"
    assert data["usage_today"] == {"calls": 3, "prompt_tokens": 1200, "completion_tokens": 90}


def test_web_page_is_served(client):
    response = client.get("/app/")

    assert response.status_code == 200
    assert "J.A.R.V.I.S." in response.text
