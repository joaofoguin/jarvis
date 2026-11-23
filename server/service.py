import json
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from server.config import Settings
from server.deepseek import DeepSeekClient
from server.models import AIUsage, Conversation, Message
from server.schemas import ChatRequest, ChatResponse
from server.tools import TOOL_DEFINITIONS, execute_tool, tool_result_message

def _message_for_model(message: Message) -> dict:
    item = {"role": message.role}
    if message.content is not None:
        item["content"] = message.content
    if message.tool_calls:
        item["tool_calls"] = message.tool_calls
    if message.tool_call_id:
        item["tool_call_id"] = message.tool_call_id
    if message.name:
        item["name"] = message.name
    return item

async def process_chat(request: ChatRequest, session: AsyncSession, settings: Settings) -> ChatResponse:
    if request.conversation_id:
        conversation = await session.get(Conversation, request.conversation_id)
        if conversation is None:
            raise ValueError("Conversa não encontrada.")
    else:
        conversation = Conversation(id=str(uuid.uuid4()), title=request.message[:157] + ("..." if len(request.message) > 157 else ""))
        session.add(conversation)
        await session.flush()

    history_result = await session.execute(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id.desc()).limit(settings.conversation_history_limit)
    )
    history = [_message_for_model(item) for item in reversed(history_result.scalars().all())]
    session.add(Message(conversation_id=conversation.id, role="user", content=request.message))
    await session.flush()

    messages = [*history, {"role": "user", "content": request.message}]
    client = DeepSeekClient(settings)
    prompt_tokens = 0
    completion_tokens = 0

    for _ in range(settings.max_tool_rounds):
        data = await client.complete(messages, TOOL_DEFINITIONS)
        choice = data.get("choices", [{}])[0]
        assistant = choice.get("message", {})
        usage = data.get("usage") or {}
        prompt_tokens += int(usage.get("prompt_tokens", 0))
        completion_tokens += int(usage.get("completion_tokens", 0))
        tool_calls = assistant.get("tool_calls") or []

        if not tool_calls:
            answer = (assistant.get("content") or "").strip() or "Desculpe, senhor. Não consegui formular uma resposta."
            session.add(Message(conversation_id=conversation.id, role="assistant", content=answer))
            session.add(AIUsage(
                provider="deepseek", model=data.get("model", settings.deepseek_model), source=request.source,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                cache_hit_tokens=int(usage.get("prompt_cache_hit_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            ))
            await session.commit()
            return ChatResponse(conversation_id=conversation.id, answer=answer, model=data.get("model", settings.deepseek_model), prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

        messages.append({"role": "assistant", "content": assistant.get("content"), "tool_calls": tool_calls})
        session.add(Message(conversation_id=conversation.id, role="assistant", content=assistant.get("content"), tool_calls=tool_calls))
        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name", "")
            call_id = call.get("id", "")
            try:
                arguments = json.loads(function.get("arguments") or "{}")
                result = await execute_tool(name, arguments, session)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                result = {"ok": False, "error": str(error)}
            tool_message = tool_result_message(call_id, name, result)
            messages.append(tool_message)
            session.add(Message(conversation_id=conversation.id, role="tool", content=tool_message["content"], tool_call_id=call_id, name=name))
        await session.flush()

    answer = "Senhor, alcancei o limite de etapas de ferramentas desta solicitação. Posso continuar se desejar."
    session.add(Message(conversation_id=conversation.id, role="assistant", content=answer))
    await session.commit()
    return ChatResponse(conversation_id=conversation.id, answer=answer, model=settings.deepseek_model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
