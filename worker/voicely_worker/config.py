import os
from pathlib import Path

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data")).resolve()
MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/models")).resolve()
RVC_DIR = Path(os.environ.get("RVC_DIR", "/opt/rvc")).resolve()
PIPER_BIN = os.environ.get("PIPER_BIN", "/opt/piper/piper")

# Queue names shared with the API (api/app/queue.py).
QUEUE_PREFIX = "voicely:jobs:"
EVENTS_KEY = "voicely:events"
CANCEL_PREFIX = "voicely:cancel:"
WORKER_PREFIX = "voicely:worker:"

# Which queues this worker serves, in priority order. Run a second worker with
# WORKER_QUEUES=train to keep long training runs from blocking conversions.
WORKER_QUEUES = [q.strip() for q in os.environ.get("WORKER_QUEUES", "fast,train").split(",") if q.strip()]

# Voice models kept in memory. Each is ~55 MB on disk but more once loaded.
VOICE_CACHE_SIZE = int(os.environ.get("VOICE_CACHE_SIZE", "2"))

# Long audio is converted in chunks of about this many seconds to bound memory.
CHUNK_SECONDS = int(os.environ.get("CHUNK_SECONDS", "30"))

# The engine's memory use creeps up across jobs. Past this resident size the
# worker exits between jobs and Docker restarts it clean (0 disables).
MAX_RSS_MB = int(os.environ.get("WORKER_MAX_RSS_MB", "5000"))

# Runs the separation model twice per window for a cleaner stem (2x slower).
MDX_DENOISE = os.environ.get("MDX_DENOISE", "0") == "1"

MDX_MODEL = MODELS_DIR / "mdx" / "UVR-MDX-NET-Voc_FT.onnx"
PIPER_DIR = MODELS_DIR / "piper"


def data_path(rel: str) -> Path:
    """Resolve a queue-supplied relative path, refusing anything outside DATA_DIR."""
    p = (DATA_DIR / rel).resolve()
    if p != DATA_DIR and DATA_DIR not in p.parents:
        raise ValueError(f"path escapes data dir: {rel}")
    return p
