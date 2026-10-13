"""The Redis contract shared with the worker (worker/voicely_worker/config.py)."""
import json

import redis

from .config import settings

QUEUE_PREFIX = "voicely:jobs:"
EVENTS_KEY = "voicely:events"
CANCEL_PREFIX = "voicely:cancel:"
WORKER_PREFIX = "voicely:worker:"

# Training goes to its own queue so a dedicated worker can take it.
QUEUE_FOR = {"train": "train"}

client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def enqueue(message: dict) -> None:
    queue = QUEUE_PREFIX + QUEUE_FOR.get(message["type"], "fast")
    client.lpush(queue, json.dumps(message))


def request_cancel(job_id: str) -> None:
    client.set(CANCEL_PREFIX + job_id, "1", ex=24 * 3600)


def workers() -> list[dict]:
    keys = list(client.scan_iter(WORKER_PREFIX + "*"))
    return [json.loads(v) for v in client.mget(keys) if v] if keys else []


def queue_depth() -> int:
    return sum(client.llen(QUEUE_PREFIX + q) for q in ("fast", "train"))
