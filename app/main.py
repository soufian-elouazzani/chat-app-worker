from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import settings
from app.db.repository import MessageRepository
from app.services.consumer import RabbitMQConsumer
from app.services.ollama import OllamaClient
from app.services.processor import TaskProcessor
from app.services.redis_store import RedisStore

LOGGER = logging.getLogger(__name__)


async def run_worker() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    redis_store = RedisStore()
    await redis_store.connect()

    message_repository: MessageRepository | None = None
    if settings.database_url:
        message_repository = MessageRepository(settings.database_url)
        await message_repository.connect()

    processor = TaskProcessor(
        redis_store=redis_store,
        ollama_client=OllamaClient(),
        message_repository=message_repository,
    )
    consumer = RabbitMQConsumer(processor=processor, redis_store=redis_store)

    stop_event = asyncio.Event()

    def _request_shutdown() -> None:
        LOGGER.info("Shutdown requested")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_shutdown)

    worker_task = asyncio.create_task(consumer.start())

    await stop_event.wait()
    await consumer.stop()
    await worker_task

    await redis_store.close()
    if message_repository is not None:
        await message_repository.close()

    LOGGER.info("Worker stopped")


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
