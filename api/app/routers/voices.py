import io
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import queue, storage
from ..config import settings
from ..db import get_db
from ..models import DatasetFile, Job, Report, User, Voice, new_id
from ..schemas import (DATASET_MIN_SECONDS, ReportIn, TrainIn, VoiceIn, VoicePatch,
                       dataset_file_out, dataset_summary, job_out, voice_out)
from ..security import current_user

router = APIRouter(prefix="/api/voices", tags=["voices"])

BUSY = {"validating", "training"}


def get_voice(voice_id: str, user: User, db: Session, owner: bool = False) -> Voice:
    """A voice the user may see (theirs, or shared); `owner` demands theirs."""
    voice = db.get(Voice, voice_id)
    if voice is None or (voice.owner_id != user.id and (owner or voice.visibility != "public")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found.")
    return voice


def usable_voice(voice_id: str, user: User, db: Session) -> Voice:
    voice = get_voice(voice_id, user, db)
    if voice.status != "ready" or not voice.model_path:
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{voice.name}' is not ready to use yet.")
    return voice


def _not_busy(voice: Voice) -> None:
    if voice.status in BUSY:
        raise HTTPException(status.HTTP_409_CONFLICT, "This voice is being processed. Try again when it finishes.")


@router.get("")
def list_voices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    shared = (Voice.visibility == "public") & (Voice.status == "ready")
    voices = db.scalars(select(Voice).where(or_(Voice.owner_id == user.id, shared))
                        .order_by(Voice.created_at.desc())).all()
    return [voice_out(v, user) for v in voices]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_voice(body: VoiceIn, request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    if not body.consent_confirmed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "You must confirm you have the right to clone this voice.")
    voice = Voice(owner_id=user.id, name=body.name.strip(), description=body.description.strip(),
                  consent_type=body.consent_type, consent_name=body.consent_name.strip(),
                  consent_ip=request.client.host if request.client else "")
    db.add(voice)
    db.commit()
    return voice_out(voice, user, detail=True)


@router.get("/{voice_id}")
def read_voice(voice_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return voice_out(get_voice(voice_id, user, db), user, detail=True)


@router.patch("/{voice_id}")
def update_voice(voice_id: str, body: VoicePatch, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    voice = get_voice(voice_id, user, db, owner=True)
    if body.name is not None:
        voice.name = body.name.strip()
    if body.description is not None:
        voice.description = body.description.strip()
    if body.visibility is not None and body.visibility != voice.visibility:
        if body.visibility == "public" and not body.sharing_confirmed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Confirm that the voice's owner agreed to let other people use it.")
        voice.visibility = body.visibility
    db.commit()
    return voice_out(voice, user, detail=True)


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voice(voice_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    voice = get_voice(voice_id, user, db, owner=True)
    for job in db.scalars(select(Job).where(Job.voice_id == voice.id,
                                            Job.status.in_(("queued", "running")),
                                            Job.type.in_(("train", "inspect")))):
        queue.request_cancel(job.id)
    db.delete(voice)
    db.commit()
    storage.remove(f"voices/{voice_id}")


# -- import an existing model ----------------------------------------------

CHECKPOINT_MESSAGE = ("G_*.pth and D_*.pth are training checkpoints, not voices. "
                      "Upload the small .pth from the 'weights' folder.")


def _unpack_model_zip(zip_path: Path, dest: Path) -> bool:
    """Pull the voice (.pth) and its index out of a zip as upload.pth and
    upload.index. Returns whether an index was found."""
    limit = settings.max_model_mb * 1024 * 1024
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That .zip file could not be opened.") from None
    with z:
        files = [i for i in z.infolist() if not i.is_dir()]
        base = lambda i: Path(i.filename).name.lower()  # noqa: E731
        voices = [i for i in files if base(i).endswith(".pth") and not base(i).startswith(("g_", "d_"))]
        indexes = [i for i in files if base(i).endswith(".index")]
        if not voices:
            only_checkpoints = any(base(i).endswith(".pth") for i in files)
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                CHECKPOINT_MESSAGE if only_checkpoints else "The zip contains no .pth voice model.")
        if len(voices) > 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "The zip contains more than one voice model. Upload one voice at a time.")
        # 'added_' is the usable index; 'trained_' is an intermediate file.
        index = next((i for i in indexes if base(i).startswith("added")), None)
        if index is None and len(indexes) == 1 and not base(indexes[0]).startswith("trained"):
            index = indexes[0]

        for member, name in ((voices[0], "upload.pth"), (index, "upload.index")):
            if member is None:
                continue
            # Sizes come from the archive's own header, so cap by bytes written.
            written = 0
            with z.open(member) as src, open(dest / name, "wb") as out:
                while chunk := src.read(1 << 20):
                    written += len(chunk)
                    if written > limit:
                        out.close()
                        (dest / name).unlink(missing_ok=True)
                        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                            f"A file inside the zip is larger than {settings.max_model_mb} MB.")
                    out.write(chunk)
        return index is not None

@router.post("/{voice_id}/model")
def upload_model(voice_id: str, model: UploadFile = File(...), index: UploadFile | None = File(None),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    voice = get_voice(voice_id, user, db, owner=True)
    _not_busy(voice)

    name = (model.filename or "").lower()
    base = f"voices/{voice.id}"
    index_rel = None

    # Everything is written under a temporary name first, so a rejected upload
    # never leaves a half-written model in place.
    if name.endswith(".zip"):
        # The bundle produced by the Colab notebook (or a zipped weights folder).
        storage.save_upload(model, f"{base}/upload.zip", settings.max_model_mb)
        try:
            if _unpack_model_zip(storage.abs_path(f"{base}/upload.zip"), storage.abs_path(base)):
                index_rel = f"{base}/upload.index"
        finally:
            storage.remove(f"{base}/upload.zip")
    else:
        if not name.endswith(".pth"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                                "Upload a .pth voice model, or the .zip from the Colab notebook.")
        if Path(name).name.startswith(("g_", "d_")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, CHECKPOINT_MESSAGE)
        if index is not None and not (index.filename or "").lower().endswith(".index"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "The index must be a .index file.")
        storage.save_upload(model, f"{base}/upload.pth", settings.max_model_mb)
        if index is not None:
            index_rel = f"{base}/upload.index"
            storage.save_upload(index, index_rel, settings.max_model_mb)

    storage.abs_path(f"{base}/upload.pth").replace(storage.abs_path(f"{base}/model.pth"))
    if index_rel:
        storage.abs_path(index_rel).replace(storage.abs_path(f"{base}/model.index"))
    else:
        storage.remove(f"{base}/model.index")

    voice.model_path = f"{base}/model.pth"
    voice.index_path = f"{base}/model.index" if index_rel else None
    voice.source, voice.status, voice.status_detail, voice.meta = "upload", "validating", "", {}

    job = Job(id=new_id(), owner_id=user.id, voice_id=voice.id, voice_name=voice.name,
              type="inspect", title=f"Check {voice.name}", hidden=True)
    db.add(job)
    db.commit()
    queue.enqueue({"id": job.id, "type": "inspect", "params": {},
                   "voice": {"model": voice.model_path, "index": voice.index_path}})
    return voice_out(voice, user, detail=True)


@router.get("/{voice_id}/model.zip")
def export_model(voice_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The voice as one zip (.pth plus index), in the layout the importer reads.
    Owner only: sharing a voice lets others use it here, not take a copy."""
    voice = get_voice(voice_id, user, db, owner=True)
    if voice.status != "ready" or not voice.model_path:
        raise HTTPException(status.HTTP_409_CONFLICT, "This voice has no finished model to download yet.")
    name = storage.safe_name(voice.name, "voice").replace(" ", "_")

    # Built on disk, not in memory: a model with its index can pass 250 MB.
    tmp_dir = storage.abs_path("work/export")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".zip", dir=tmp_dir)
    with zipfile.ZipFile(open(fd, "wb"), "w", zipfile.ZIP_STORED) as z:
        z.write(storage.abs_path(voice.model_path), f"{name}.pth")
        if voice.index_path:
            z.write(storage.abs_path(voice.index_path), f"added_{name}.index")
    return FileResponse(tmp, media_type="application/zip", filename=f"{name}-voicely.zip",
                        background=BackgroundTask(Path(tmp).unlink, missing_ok=True))


# -- build from recordings --------------------------------------------------

@router.post("/{voice_id}/dataset")
def add_recordings(voice_id: str, files: list[UploadFile] = File(...),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    voice = get_voice(voice_id, user, db, owner=True)
    _not_busy(voice)
    budget = settings.max_dataset_minutes * 60 - sum(f.duration for f in voice.dataset)

    added, rejected = [], []
    for upload in files:
        try:
            ext = storage.audio_ext(upload)
            fid = new_id()
            rel = f"voices/{voice.id}/dataset/{fid}{ext}"
            path = storage.save_upload(upload, rel, settings.max_upload_mb)
            try:
                analysis = storage.analyze_recording(path)
                if analysis["duration"] > budget:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                        f"This voice already has {settings.max_dataset_minutes} minutes of recordings.")
            except HTTPException:
                path.unlink(missing_ok=True)
                raise
            budget -= analysis["duration"]
            row = DatasetFile(id=fid, voice_id=voice.id, filename=upload.filename or "recording",
                              path=rel, duration=analysis["duration"], analysis=analysis)
            db.add(row)
            added.append(row)
        except HTTPException as e:
            rejected.append({"filename": upload.filename, "reason": e.detail})
    db.commit()
    db.refresh(voice)
    return {"added": [dataset_file_out(f) for f in added], "rejected": rejected,
            "dataset_summary": dataset_summary(voice.dataset)}


@router.delete("/{voice_id}/dataset/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_recording(voice_id: str, file_id: str, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    voice = get_voice(voice_id, user, db, owner=True)
    _not_busy(voice)
    row = db.get(DatasetFile, file_id)
    if row is None or row.voice_id != voice.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found.")
    storage.remove(row.path)
    db.delete(row)
    db.commit()


@router.get("/{voice_id}/dataset.zip")
def export_dataset(voice_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The recordings as one zip, for training elsewhere (for example Colab)."""
    voice = get_voice(voice_id, user, db, owner=True)
    if not voice.dataset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This voice has no recordings yet.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for n, f in enumerate(voice.dataset, 1):
            z.write(storage.abs_path(f.path), f"{n:03d}_{storage.safe_name(f.filename)}{Path(f.path).suffix}")
    buf.seek(0)
    name = storage.safe_name(voice.name, "voice")
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{name}-dataset.zip"'})


@router.post("/{voice_id}/consent-audio")
def upload_consent_audio(voice_id: str, file: UploadFile = File(...),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A spoken consent statement, kept with the voice as its consent record."""
    voice = get_voice(voice_id, user, db, owner=True)
    rel = f"voices/{voice.id}/consent{storage.audio_ext(file)}"
    path = storage.save_upload(file, rel, 20)
    try:
        storage.probe_duration(path)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    voice.consent_audio = rel
    db.commit()
    return voice_out(voice, user, detail=True)


@router.post("/{voice_id}/train", status_code=status.HTTP_202_ACCEPTED)
def train_voice(voice_id: str, body: TrainIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    voice = get_voice(voice_id, user, db, owner=True)
    _not_busy(voice)
    summary = dataset_summary(voice.dataset)
    if summary["voiced_seconds"] < DATASET_MIN_SECONDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, summary["text"])

    job = Job(id=new_id(), owner_id=user.id, voice_id=voice.id, voice_name=voice.name, type="train",
              title=f"Train {voice.name}", params=body.model_dump())
    voice.status, voice.status_detail = "training", ""
    db.add(job)
    db.commit()
    queue.enqueue({"id": job.id, "type": "train", "params": job.params,
                   "dataset_dir": f"voices/{voice.id}/dataset", "voice_dir": f"voices/{voice.id}"})
    return job_out(job)


@router.post("/{voice_id}/report", status_code=status.HTTP_201_CREATED)
def report_voice(voice_id: str, body: ReportIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    voice = get_voice(voice_id, user, db)
    db.add(Report(voice_id=voice.id, reporter_id=user.id, reason=body.reason.strip()))
    db.commit()
    return {"ok": True}
