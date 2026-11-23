import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from server.config import Settings
from server.database import Base
from server.models import Task
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

def test_tool_definitions_are_unique_and_have_schemas():
    names = [item["function"]["name"] for item in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))
    assert "create_task" in names
    assert "list_tasks" in names
    assert all(item["function"]["parameters"]["type"] == "object" for item in TOOL_DEFINITIONS)

def test_settings_default_to_current_deepseek_model():
    settings = Settings(_env_file=None, deepseek_api_key="test")
    assert settings.deepseek_model == "deepseek-flash"
