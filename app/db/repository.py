from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.schemas.task import ChatMessage

LOGGER = logging.getLogger(__name__)

metadata = MetaData()

messages_table = Table(
    "messages",
    metadata,
    Column("message_id", String, primary_key=True),
    Column("session_id", String, nullable=False),
    Column("role", String, nullable=False),
    Column("content", Text, nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("token_count", Integer),
)


class MessageRepository:
    def __init__(self, database_url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def connect(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        LOGGER.info("Connected to PostgreSQL")

    async def close(self) -> None:
        await self.engine.dispose()

    async def list_session_messages(self, session_id: UUID) -> list[ChatMessage]:
        query = (
            select(
                messages_table.c.message_id,
                messages_table.c.session_id,
                messages_table.c.role,
                messages_table.c.content,
                messages_table.c.timestamp,
                messages_table.c.token_count,
            )
            .where(messages_table.c.session_id == str(session_id))
            .order_by(messages_table.c.timestamp.asc())
        )

        async with self.engine.connect() as conn:
            rows = (await conn.execute(query)).all()

        return [
            ChatMessage(
                message_id=row.message_id,
                session_id=row.session_id,
                role=row.role,
                content=row.content,
                timestamp=row.timestamp,
                token_count=row.token_count,
            )
            for row in rows
        ]

    async def save_message(self, message: ChatMessage) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                messages_table.insert().values(
                    message_id=message.message_id,
                    session_id=message.session_id,
                    role=message.role,
                    content=message.content,
                    timestamp=message.timestamp,
                    token_count=message.token_count,
                )
            )
