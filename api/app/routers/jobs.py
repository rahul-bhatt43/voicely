import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import queue, storage
from ..config import settings
from ..db import get_db
from ..models import Job, User, Voice, new_id
from ..schemas import ConversionParams, CoverParams, TTSIn, job_out
from ..security import current_user
from .voices import usable_voice

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ACTIVE = ("queued", "running")


def _check_quota(user: User, db: Session) -> None:
    active = db.scalar(select(func.count()).select_from(Job).where(
        Job.owner_id == user.id, Job.status.in_(ACTIVE), Job.hidden.is_(False)))
    if active >= settings.max_active_jobs_per_user:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"You already have {active} jobs in progress. Wait for one to finish.")


def _parse(model, raw: str):
    try:
        return model.model_validate(json.loads(raw or "{}"))
    except (ValidationError, json.JSONDecodeError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid settings: {e}") from None


def _submit(db: Session, job: Job, voice: Voice, input_rel: str | None) -> dict:
    db.add(job)
    db.commit()
    queue.enqueue({
        "id": job.id, "type": job.type, "title": job.title, "params": job.params,
        "input": input_rel, "out_dir": f"jobs/{job.id}",
        "voice": {"model": voice.model_path, "index": voice.index_path},
    })
    return job_out(job)


def _audio_job(kind: str, params, voice_id: str, title: str, file: UploadFile,
               user: User, db: Session) -> dict:
    _check_quota(user, db)
    voice = usable_voice(voice_id, user, db)
    job_id = new_id()
    rel = f"jobs/{job_id}/input{storage.audio_ext(file)}"
    path = storage.save_upload(file, rel, settings.max_upload_mb)
    try:
        seconds = storage.probe_duration(path)
        if seconds > settings.max_audio_minutes * 60:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Audio is limited to {settings.max_audio_minutes} minutes per job.")
    except HTTPException:
        storage.remove(f"jobs/{job_id}")
        raise
    job = Job(id=job_id, owner_id=user.id, voice_id=voice.id, voice_name=voice.name, type=kind,
              title=title.strip()[:200] or storage.safe_name(file.filename or ""),
              params=params.model_dump(), input_path=rel, meta={"input_seconds": round(seconds, 1)})
    return _submit(db, job, voice, rel)


@router.post("/convert", status_code=status.HTTP_202_ACCEPTED)
def create_conversion(file: UploadFile = File(...), voice_id: str = Form(...), title: str = Form(""),
                      params: str = Form("{}"), user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    """Re-voice a clean recording of speech or singing."""
    return _audio_job("convert", _parse(ConversionParams, params), voice_id, title, file, user, db)


@router.post("/cover", status_code=status.HTTP_202_ACCEPTED)
def create_cover(file: UploadFile = File(...), voice_id: str = Form(...), title: str = Form(""),
                 params: str = Form("{}"), user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """Full song in, cover out: separate vocals, convert them, mix back."""
    return _audio_job("cover", _parse(CoverParams, params), voice_id, title, file, user, db)


@router.post("/tts", status_code=status.HTTP_202_ACCEPTED)
def create_tts(body: TTSIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Text in a custom voice: a narrator speaks it, then RVC re-voices it."""
    text = body.text.strip()
    if len(text) > settings.max_tts_chars:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Text is limited to {settings.max_tts_chars} characters.")
    _check_quota(user, db)
    voice = usable_voice(body.voice_id, user, db)
    params = body.model_dump(exclude={"voice_id", "title"}) | {"text": text}
    job = Job(id=new_id(), owner_id=user.id, voice_id=voice.id, voice_name=voice.name, type="tts",
              title=body.title.strip() or text[:60], params=params)
    return _submit(db, job, voice, None)


@router.get("")
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.owner_id == user.id, Job.hidden.is_(False))
                      .order_by(Job.created_at.desc()).limit(200)).all()
    return [job_out(j) for j in jobs]


def _own_job(job_id: str, user: User, db: Session) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return job


@router.get("/{job_id}")
def read_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return job_out(_own_job(job_id, user, db))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _own_job(job_id, user, db)
    if job.status in ACTIVE:
        # A running job stops at the worker's next checkpoint and reports back;
        # a queued one is skipped when the worker reaches it.
        queue.request_cancel(job.id)
        if job.status == "queued":
            job.status, job.finished_at = "canceled", datetime.now(timezone.utc)
            voice = db.get(Voice, job.voice_id) if job.type == "train" and job.voice_id else None
            if voice is not None and voice.status == "training":
                voice.status = "ready" if voice.model_path else "draft"
            db.commit()
    return job_out(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _own_job(job_id, user, db)
    if job.status in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the job before deleting it.")
    db.delete(job)
    db.commit()
    storage.remove(f"jobs/{job.id}")
