from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class Settings:
    rabbitmq_url: str = field(
        default_factory=lambda: os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))

    chat_queue: str = field(default_factory=lambda: os.getenv("CHAT_QUEUE", "chat_tasks"))
    chat_dlq: str = field(default_factory=lambda: os.getenv("CHAT_DLQ", "chat_tasks.dlq"))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    prefetch_count: int = field(default_factory=lambda: int(os.getenv("PREFETCH_COUNT", "1")))

    session_cache_size: int = field(default_factory=lambda: int(os.getenv("SESSION_CACHE_SIZE", "50")))
    session_cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("SESSION_CACHE_TTL_SECONDS", "3600"))
    )
    ollama_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


settings = Settings()
