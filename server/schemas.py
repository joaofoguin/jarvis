from typing import Literal
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None
    source: Literal["desktop", "mobile", "web"] = "web"

class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    created_at: str
