import datetime

import pytest
from fastapi.testclient import TestClient

import main


TOKEN = "segredo-de-teste"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", TOKEN)
    test_client = TestClient(main.app)
    test_client.finished = []

    monkeypatch.setattr(main, "enqueue_agent_command", lambda command: 7)
    monkeypatch.setattr(main, "list_pending_commands", lambda: [
        (7, "open_app:notepad", "pending", datetime.datetime(2026, 10, 22))
    ])

    def finish(command_id, status, result):
        test_client.finished.append((command_id, status, result))
        return (command_id, "open_app:notepad", status)

    monkeypatch.setattr(main, "finish_agent_command", finish)
    return test_client


@pytest.mark.parametrize("method, path", [
    ("get", "/agent/commands"),
    ("post", "/agent/command"),
    ("post", "/agent/commands/7/complete"),
])
def test_routes_reject_missing_or_wrong_token(client, method, path):
    body = {"command": "open_app:notepad"}

    assert client.request(method, path, json=body).status_code == 401
    assert client.request(method, path, json=body, headers={"Authorization": "Bearer errado"}).status_code == 401


def test_queue_is_closed_when_server_has_no_token(client, monkeypatch):
    monkeypatch.delenv("AGENT_TOKEN")

    assert client.get("/agent/commands", headers=AUTH).status_code == 503


def test_lists_pending_commands_with_token(client):
    response = client.get("/agent/commands", headers=AUTH)

    assert response.json() == [{
        "id": 7,
        "command": "open_app:notepad",
        "status": "pending",
        "created_at": "2026-10-22T00:00:00"
    }]


def test_create_command_only_accepts_allowed_commands(client):
    assert client.post("/agent/command", json={"command": "open_app:notepad"}, headers=AUTH).status_code == 200
    assert client.post("/agent/command", json={"command": "del C:\\"}, headers=AUTH).status_code == 400


def test_complete_records_status_and_result(client):
    response = client.post(
        "/agent/commands/7/complete",
        json={"status": "failed", "result": "x" * 600},
        headers=AUTH
    )

    assert response.json()["status"] == "failed"
    assert client.finished == [(7, "failed", "x" * 500)]


def test_complete_without_body_means_completed(client):
    client.post("/agent/commands/7/complete", headers=AUTH)

    assert client.finished == [(7, "completed", None)]


def test_complete_rejects_unknown_status(client):
    response = client.post("/agent/commands/7/complete", json={"status": "hacked"}, headers=AUTH)

    assert response.status_code == 422


def test_status_route_stays_public(client):
    assert client.get("/agent/status").status_code == 200


def test_create_accepts_claude_code_tasks(client):
    response = client.post("/agent/command", json={"command": "claude_code:criar hello.py"}, headers=AUTH)

    assert response.status_code == 200
