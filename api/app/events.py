"""Applies worker events to the database.

The worker has no database access; it pushes small JSON events onto a Redis
list and this consumer (one asyncio task inside the API process) is the only
writer of job results.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import Job, Voice
from .queue import EVENTS_KEY

log = logging.getLogger("voicely.events")

TERMINAL = {"succeeded", "failed", "canceled"}


def _finish_voice(db, job: Job) -> None:
    """Carry the result of a train/inspect job over to its voice."""
    voice = db.get(Voice, job.voice_id) if job.voice_id else None
    if voice is None:
        return
    if job.status == "succeeded":
        voice.status, voice.status_detail = "ready", ""
        voice.meta = {**(voice.meta or {}), **job.meta}
        if job.type == "train":
            voice.source = "trained"
            voice.model_path = f"voices/{voice.id}/model.pth"
            voice.index_path = f"voices/{voice.id}/model.index"
    elif job.type == "train" and voice.model_path:
        # A failed or canceled retrain leaves the previous model usable.
        voice.status = "ready"
        voice.status_detail = "The last training run did not finish; the earlier model is still in use."
    elif job.status == "canceled":
        voice.status, voice.status_detail = "draft", ""
    else:
        voice.status, voice.status_detail = "failed", job.error


def apply_event(event: dict) -> None:
    with SessionLocal() as db:
        job = db.get(Job, event.get("job_id"))
        if job is None or job.status in TERMINAL:
            return
        now = datetime.now(timezone.utc)
        job.heartbeat_at = now

        if "progress" in event:
            job.progress = max(job.progress, float(event["progress"]))
        if "stage" in event:
            job.stage = str(event["stage"])[:120]
        if "log" in event:
            job.log = str(event["log"])[-6000:]

        status = event.get("status")
        if status == "running":
            job.status, job.started_at = "running", job.started_at or now
        elif status in TERMINAL:
            job.status, job.finished_at = status, now
            job.error = str(event.get("error", ""))[:2000]
            job.outputs = event.get("outputs") or {}
            job.meta = event.get("meta") or {}
            job.seconds = event.get("seconds")
            if status == "succeeded":
                job.progress = 1.0
            if job.type in ("train", "inspect"):
                _finish_voice(db, job)
        db.commit()


def reap_stale() -> None:
    """Fail running jobs whose worker went away (crash, OOM kill, restart)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.job_stale_seconds)
    with SessionLocal() as db:
        stale = db.scalars(select(Job).where(Job.status == "running", Job.heartbeat_at < cutoff)).all()
        for job in stale:
            log.warning("job %s lost its worker", job.id)
            job.status, job.finished_at = "failed", datetime.now(timezone.utc)
            job.error = ("The worker stopped while processing this job, most often because it "
                         "ran out of memory. Try again with a shorter file.")
            if job.type in ("train", "inspect"):
                _finish_voice(db, job)
        db.commit()


async def consume() -> None:
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    last_reap = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            item = await r.brpop(EVENTS_KEY, timeout=5)
            if item:
                await asyncio.to_thread(apply_event, json.loads(item[1]))
            if loop.time() - last_reap > 30:
                last_reap = loop.time()
                await asyncio.to_thread(reap_stale)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep consuming whatever one event does
            log.exception("event consumer error")
            await asyncio.sleep(2)
