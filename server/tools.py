import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from server.models import Task

TOOL_DEFINITIONS = [
    {"type": "function", "function": {
        "name": "create_task",
        "description": "Cria uma tarefa na lista pessoal do usuário. Use quando ele pedir para anotar, registrar ou organizar uma tarefa.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "Título curto da tarefa."},
            "description": {"type": "string", "description": "Detalhes opcionais da tarefa."}
        }, "required": ["title"], "additionalProperties": False}
    }},
    {"type": "function", "function": {
        "name": "list_tasks",
        "description": "Lista as tarefas pessoais ainda não concluídas do usuário.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
    }}
]

async def execute_tool(name: str, arguments: dict[str, Any], session: AsyncSession) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("Os argumentos precisam ser um objeto JSON.")
    if name == "create_task":
        title = str(arguments.get("title", "")).strip()
        description = str(arguments.get("description", "")).strip()
        if not title or len(title) > 160:
            raise ValueError("O título precisa ter entre 1 e 160 caracteres.")
        if len(description) > 4000:
            raise ValueError("A descrição excede 4.000 caracteres.")
        task = Task(title=title, description=description, status="pending")
        session.add(task)
        await session.flush()
        await session.refresh(task)
        return {"ok": True, "task": {"id": task.id, "title": task.title, "description": task.description, "status": task.status}}
    if name == "list_tasks":
        result = await session.execute(select(Task).where(Task.status != "completed").order_by(Task.created_at.desc()).limit(30))
        tasks = result.scalars().all()
        return {"ok": True, "tasks": [{"id": x.id, "title": x.title, "description": x.description, "status": x.status} for x in tasks]}
    raise ValueError("Ferramenta não registrada: " + name)

def tool_result_message(tool_call_id: str, name: str, result: dict[str, Any]) -> dict[str, str]:
    return {"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": json.dumps(result, ensure_ascii=False)}
