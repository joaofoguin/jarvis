import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.app import create_app
from server.config import Settings
from server.database import Base
from server.deepseek import DeepSeekClient
from server.models import AIUsage, Task
from server.schemas import ChatRequest
from server.service import process_chat
from server.tools import TOOL_DEFINITIONS, execute_tool


@pytest.mark.asyncio
async def test_create_task_tool_persists_task():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        result = await execute_tool("create_task", {
            "title": "Revisar redes",
            "description": "Estudar a camada de transporte"
        }, session)
        await session.commit()
        assert result["ok"] is True
        assert result["task"]["title"] == "Revisar redes"
        assert result["task"]["status"] == "pending"
    async with sessions() as session:
        task = await session.get(Task, 1)
        assert task is not None
        assert task.description == "Estudar a camada de transporte"
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_task_rejects_empty_title():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        with pytest.raises(ValueError):
            await execute_tool("create_task", {"title": "  "}, session)
    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_executes_deepseek_tool_call_and_logs_each_model_round(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    calls = []

    async def fake_complete(self, messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            return {
                "model": "deepseek-flash",
                "choices": [{"message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_create_task",
                        "type": "function",
                        "function": {
                            "name": "create_task",
                            "arguments": json.dumps({"title": "Estudar banco de dados"})
                        }
                    }]
                }}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 10}
            }
        assert messages[-1]["role"] == "tool"
        return {
            "model": "deepseek-flash",
            "choices": [{"message": {"role": "assistant", "content": "Tarefa registrada, senhor."}}],
            "usage": {"prompt_tokens": 130, "completion_tokens": 12, "prompt_cache_hit_tokens": 15}
        }

    monkeypatch.setattr(DeepSeekClient, "complete", fake_complete)
    settings = Settings(_env_file=None, deepseek_api_key="test", max_tool_rounds=3)

    async with sessions() as session:
        result = await process_chat(
            ChatRequest(message="Anote que preciso estudar banco de dados.", source="desktop"),
            session,
            settings,
        )
        assert result.answer == "Tarefa registrada, senhor."
        assert result.prompt_tokens == 230
        assert result.completion_tokens == 32

    async with sessions() as session:
        tasks = (await session.execute(select(Task))).scalars().all()
        usage = (await session.execute(select(AIUsage))).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].title == "Estudar banco de dados"
        assert len(usage) == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_api_health_and_private_route_authentication(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///" + str(tmp_path / "jarvis.db"),
        jarvis_api_token="test-secret",
        auto_create_schema=True,
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            live = await client.get("/health/live")
            ready = await client.get("/health/ready")
            denied = await client.post("/api/v1/chat", json={"message": "Olá"})

            assert live.status_code == 200
            assert ready.status_code == 200
            assert denied.status_code == 401

    # O lifespan encerra o engine da aplicação.


def test_tool_definitions_are_unique_and_have_schemas():
    names = [item["function"]["name"] for item in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))
    assert "create_task" in names
    assert "list_tasks" in names
    assert all(item["function"]["parameters"]["type"] == "object" for item in TOOL_DEFINITIONS)


def test_settings_default_to_current_deepseek_model():
    settings = Settings(_env_file=None, deepseek_api_key="test")
    assert settings.deepseek_model == "deepseek-flash"
