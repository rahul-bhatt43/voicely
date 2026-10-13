import mimetypes

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from .. import queue, storage
from ..config import settings
from ..models import User
from ..security import current_user, read_file_token

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/system")
def system(user: User = Depends(current_user)):
    """What the engine can do right now, so the UI can explain waits honestly."""
    workers = queue.workers()
    ready = [w for w in workers if w.get("device") and not w.get("missing_models")]
    gpu = next((w["gpu"] for w in ready if w.get("gpu")), None)
    if ready:
        state = "ready"
    elif workers:
        state = "starting"  # worker is up but still loading or waiting for models
    else:
        state = "offline"
    return {
        "engine": state,
        "device": "gpu" if gpu else ("cpu" if ready else None),
        "gpu": gpu,
        "can_train": any("train" in w.get("queues", []) for w in ready),
        "queued": queue.queue_depth(),
        "busy": sum(1 for w in workers if w.get("busy")),
        "tts_voices": next((w["tts_voices"] for w in workers if w.get("tts_voices")), []),
        "limits": {
            "max_upload_mb": settings.max_upload_mb,
            "max_audio_minutes": settings.max_audio_minutes,
            "max_tts_chars": settings.max_tts_chars,
            "max_dataset_minutes": settings.max_dataset_minutes,
        },
    }


@router.get("/files/{token}")
def serve_file(token: str):
    data = read_file_token(token)
    path = storage.abs_path(data["p"])
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # A filename in the token marks a download link; without one, play inline.
    return FileResponse(path, media_type=media, filename=data.get("n"),
                        content_disposition_type="attachment" if data.get("n") else "inline")
