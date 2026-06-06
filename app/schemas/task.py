from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatTaskPayload(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: UUID
    prompt: str = Field(min_length=1)
    model: str = Field(min_length=1)
    timestamp: datetime


class ChatMessage(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    timestamp: datetime
    model: str | None = None
    token_count: int | None = None


class TaskResult(BaseModel):
    message: ChatMessage
    provider: str = "ollama"
