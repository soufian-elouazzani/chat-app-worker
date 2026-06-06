from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.schemas.task import ChatMessage, TaskResult

LOGGER = logging.getLogger(__name__)

TaskStatus = Literal["pending", "completed", "failed"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RedisStore:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.redis_url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._client = redis.from_url(self.redis_url, decode_responses=True)
        await self._client.ping()
        LOGGER.info("Connected to Redis")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client is not connected")
        return self._client

    def _task_key(self, task_id: UUID) -> str:
        return f"task:{task_id}"

    def _session_key(self, session_id: UUID) -> str:
        return f"chat:session:{session_id}:messages"

    async def get_retry_count(self, task_id: UUID) -> int:
        value = await self.client.hget(self._task_key(task_id), "retry_count")
        return int(value or 0)

    async def set_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        *,
        result: TaskResult | None = None,
        error: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        key = self._task_key(task_id)
        payload: dict[str, str] = {"status": status}

        if result is not None:
            payload["result"] = result.model_dump_json()
        if error is not None:
            payload["error"] = error
        if retry_count is not None:
            payload["retry_count"] = str(retry_count)

        payload["updated_at"] = _utc_now().isoformat()

        await self.client.hset(key, mapping=payload)
        LOGGER.debug("Updated task %s status=%s", task_id, status)

    async def get_session_messages(self, session_id: UUID) -> list[ChatMessage]:
        key = self._session_key(session_id)
        raw_messages = await self.client.zrange(key, 0, -1)

        messages: list[ChatMessage] = []
        for raw in raw_messages:
            try:
                messages.append(ChatMessage.model_validate_json(raw))
            except Exception:
                LOGGER.warning("Skipping invalid cached message in %s", key)

        return messages

    async def append_session_message(self, message: ChatMessage) -> None:
        key = self._session_key(UUID(message.session_id))
        score = message.timestamp.timestamp()
        payload = message.model_dump_json()

        async with self.client.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {payload: score})
            pipe.zremrangebyrank(key, 0, -(settings.session_cache_size + 1))
            pipe.expire(key, settings.session_cache_ttl_seconds)
            await pipe.execute()
