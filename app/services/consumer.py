from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aio_pika
from aio_pika import IncomingMessage, Message
from aio_pika.abc import AbstractRobustConnection

from app.core.config import settings
from app.schemas.task import ChatTaskPayload
from app.services.processor import TaskProcessor

if TYPE_CHECKING:
    from app.db.repository import MessageRepository
    from app.services.redis_store import RedisStore

LOGGER = logging.getLogger(__name__)

RETRY_HEADER = "x-retry-count"


class RabbitMQConsumer:
    def __init__(
        self,
        processor: TaskProcessor,
        redis_store: RedisStore,
        rabbitmq_url: str | None = None,
    ) -> None:
        self.processor = processor
        self.redis_store = redis_store
        self.rabbitmq_url = rabbitmq_url or settings.rabbitmq_url
        self._connection: AbstractRobustConnection | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=settings.prefetch_count)

        await channel.declare_queue(settings.chat_dlq, durable=True)

        queue = await channel.declare_queue(
            settings.chat_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": settings.chat_dlq,
            },
        )

        LOGGER.info(
            "Listening on queue=%s (dlq=%s, max_retries=%d)",
            settings.chat_queue,
            settings.chat_dlq,
            settings.max_retries,
        )

        await queue.consume(self._handle_message)

        await self._stop_event.wait()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _handle_message(self, message: IncomingMessage) -> None:
        retry_count = self._get_retry_count(message)

        try:
            payload = ChatTaskPayload.model_validate_json(message.body.decode())
        except Exception as exc:
            LOGGER.exception("Invalid task payload: %s", exc)
            await message.reject(requeue=False)
            return

        try:
            await self.processor.process(payload)
            await message.ack()
        except Exception as exc:
            LOGGER.exception("Task %s failed on attempt %d", payload.task_id, retry_count + 1)

            next_retry = retry_count + 1
            await self.redis_store.set_task_status(
                payload.task_id,
                "pending" if next_retry < settings.max_retries else "failed",
                error=str(exc),
                retry_count=next_retry,
            )

            if next_retry < settings.max_retries:
                await self._republish_with_retry(message, next_retry)
                await message.ack()
            else:
                await self.processor.mark_failed(payload.task_id, str(exc), next_retry)
                await message.reject(requeue=False)

    def _get_retry_count(self, message: IncomingMessage) -> int:
        header_value = message.headers.get(RETRY_HEADER) if message.headers else None
        if header_value is None:
            return 0
        return int(header_value)

    async def _republish_with_retry(self, message: IncomingMessage, retry_count: int) -> None:
        if self._connection is None:
            raise RuntimeError("RabbitMQ connection is not available")

        channel = await self._connection.channel()
        await channel.default_exchange.publish(
            Message(
                body=message.body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type=message.content_type or "application/json",
                headers={**(message.headers or {}), RETRY_HEADER: retry_count},
            ),
            routing_key=settings.chat_queue,
        )
        LOGGER.info("Requeued message with retry_count=%d", retry_count)
