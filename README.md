# Chat App Worker

Async worker service for the multi-model AI chat platform. It consumes inference tasks from RabbitMQ, loads conversation context from Redis (with PostgreSQL fallback), calls Ollama, and writes results back to Redis and the database.

## Role in the system

```
Frontend → Nginx → API Gateway → RabbitMQ → Worker → Ollama
                         ↓                      ↓
                       Redis  ←──────────────  Redis
                         ↓
                    PostgreSQL ←────────── Worker
```

1. The gateway accepts a chat message and publishes a task to the `chat_tasks` queue.
2. This worker picks up the task, builds context, and calls Ollama.
3. The assistant reply is persisted and the task status in Redis becomes `completed`.
4. The frontend polls the gateway until the task is done.

## Quick start

### Prerequisites

- Python 3.12+
- Running RabbitMQ, Redis, and Ollama (use `docker compose up` below)
- Optional: PostgreSQL for durable message history

### Local run

```bash
uv sync
uv run python -m app.main
```

### Docker Compose (worker + dependencies)

```bash
docker compose up --build
```

Pull a model into Ollama first:

```bash
docker compose exec ollama ollama pull llama3
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `DATABASE_URL` | *(empty)* | Optional PostgreSQL URL (`postgresql+asyncpg://...`) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `CHAT_QUEUE` | `chat_tasks` | Main task queue |
| `CHAT_DLQ` | `chat_tasks.dlq` | Dead-letter queue |
| `MAX_RETRIES` | `3` | Retries before sending to DLQ |
| `PREFETCH_COUNT` | `1` | In-flight tasks per worker |
| `SESSION_CACHE_SIZE` | `50` | Recent messages kept in Redis |
| `SESSION_CACHE_TTL_SECONDS` | `3600` | Redis session cache TTL |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | HTTP timeout for inference |
| `LOG_LEVEL` | `INFO` | Logging level |

## RabbitMQ payload

The gateway publishes JSON tasks in this shape:

```json
{
  "task_id": "uuid",
  "session_id": "uuid",
  "user_id": "uuid",
  "prompt": "Hello",
  "model": "llama3",
  "timestamp": "2026-06-06T12:00:00Z"
}
```

## Redis keys

| Key | Purpose |
|-----|---------|
| `task:{task_id}` | Task status hash (`status`, `result`, `error`, `retry_count`) |
| `chat:session:{session_id}:messages` | Sorted set of recent messages (last 50, 1h TTL) |

Completed tasks store a result compatible with the gateway API:

```json
{
  "message": {
    "message_id": "uuid",
    "session_id": "uuid",
    "role": "assistant",
    "content": "...",
    "timestamp": "...",
    "model": "llama3"
  },
  "provider": "ollama"
}
```

## Project layout

```
app/
  main.py                 # Worker entrypoint
  core/config.py          # Environment settings
  schemas/task.py         # Task and message models
  services/
    consumer.py           # RabbitMQ consumer with retry/DLQ
    processor.py          # Task orchestration
    ollama.py             # Ollama HTTP client
    redis_store.py        # Task status and session cache
  db/repository.py        # Optional PostgreSQL persistence
main.py                   # CLI wrapper
docker-compose.yml        # Local stack for development
Dockerfile
```

## Gateway integration

When wiring the gateway to RabbitMQ and Redis:

1. Set `ENABLE_DEMO_WORKER=false` on the gateway.
2. Publish tasks to `chat_tasks` using the payload above.
3. Write the user message to Redis and set `task:{task_id}` to `pending` before publishing.
4. Read task status from Redis in `GET /tasks/{task_id}/status`.

See the [chat-app-gateway](https://github.com/) repository for the API contract.

## License

MIT
