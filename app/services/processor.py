from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.core.config import settings
from app.db.repository import MessageRepository
from app.schemas.task import ChatMessage, ChatTaskPayload, TaskResult
from app.services.ollama import OllamaClient
from app.services.redis_store import RedisStore

LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskProcessor:
    def __init__(
        self,
        redis_store: RedisStore,
        ollama_client: OllamaClient,
        message_repository: MessageRepository | None = None,
    ) -> None:
        self.redis_store = redis_store
        self.ollama_client = ollama_client
        self.message_repository = message_repository

    async def process(self, task: ChatTaskPayload) -> TaskResult:
        LOGGER.info(
            "Processing task=%s session=%s model=%s",
            task.task_id,
            task.session_id,
            task.model,
        )

        history = await self._load_history(task.session_id)
        ollama_messages = [
            {"role": message.role, "content": message.content}
            for message in history
            if message.role in {"user", "assistant"}
        ]

        if not ollama_messages or ollama_messages[-1]["content"] != task.prompt:
            ollama_messages.append({"role": "user", "content": task.prompt})

        assistant_content = await self.ollama_client.generate(task.model, ollama_messages)

        assistant_message = ChatMessage(
            message_id=str(uuid4()),
            session_id=str(task.session_id),
            role="assistant",
            content=assistant_content,
            timestamp=_utc_now(),
            model=task.model,
        )

        if self.message_repository is not None:
            await self.message_repository.save_message(assistant_message)

        await self.redis_store.append_session_message(assistant_message)

        result = TaskResult(message=assistant_message, provider="ollama")
        await self.redis_store.set_task_status(task.task_id, "completed", result=result)

        LOGGER.info("Completed task=%s", task.task_id)
        return result

    async def mark_failed(self, task_id: UUID, error: str, retry_count: int) -> None:
        await self.redis_store.set_task_status(
            task_id,
            "failed",
            error=error,
            retry_count=retry_count,
        )

    async def _load_history(self, session_id: UUID) -> list[ChatMessage]:
        cached = await self.redis_store.get_session_messages(session_id)
        if cached:
            return cached

        if self.message_repository is not None:
            messages = await self.message_repository.list_session_messages(session_id)
            for message in messages[-settings.session_cache_size :]:
                await self.redis_store.append_session_message(message)
            return messages

        return []
