from typing import Literal

from pydantic import BaseModel, Field

from .models import DatasetFile, Job, User, Voice
from .storage import file_url, safe_name

# How much clean speech a voice needs. Below MIN the trainer is refused;
# GOOD is where results usually become convincing.
DATASET_MIN_SECONDS = 120
DATASET_GOOD_SECONDS = 600


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: str
    password: str


class VoiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    consent_type: Literal["self", "permission"]
    consent_name: str = Field(min_length=2, max_length=120)
    consent_confirmed: bool


class VoicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    visibility: Literal["private", "public"] | None = None
    # Required when making a voice public: sharing widens what consent covers.
    sharing_confirmed: bool = False


class TrainIn(BaseModel):
    epochs: int = Field(default=200, ge=1, le=1000)
    batch_size: int = Field(default=4, ge=1, le=32)


class ReportIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class ConversionParams(BaseModel):
    """Engine settings, named as in RVC_ARCHITECTURE.md section 3."""

    pitch: int = Field(default=0, ge=-24, le=24)
    f0_method: Literal["rmvpe", "harvest", "pm", "crepe", "mangio-crepe"] = "rmvpe"
    index_rate: float = Field(default=0.66, ge=0, le=1)
    filter_radius: int = Field(default=3, ge=0, le=7)
    rms_mix_rate: float = Field(default=0.21, ge=0, le=1)
    protect: float = Field(default=0.33, ge=0, le=0.5)
    format: Literal["mp3", "wav", "flac"] = "mp3"


class CoverParams(ConversionParams):
    song_key: int = Field(default=0, ge=-6, le=6)
    vocal_gain_db: float = Field(default=0, ge=-12, le=12)
    inst_gain_db: float = Field(default=0, ge=-12, le=12)
    reverb: float = Field(default=0.15, ge=0, le=1)


class TTSIn(ConversionParams):
    voice_id: str
    text: str = Field(min_length=1)
    tts_voice: str
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    title: str = Field(default="", max_length=200)


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name}


def dataset_summary(files: list[DatasetFile]) -> dict:
    total = sum(f.duration for f in files)
    voiced = sum(f.analysis.get("voiced_seconds", f.duration) for f in files)
    flagged = sum(1 for f in files if any(i["level"] == "bad" for i in f.analysis.get("issues", [])))
    if voiced >= DATASET_GOOD_SECONDS:
        level, text = "good", "Enough material for a convincing voice."
    elif voiced >= DATASET_MIN_SECONDS:
        level, text = "ok", "Enough to train, but 10 minutes or more gives a noticeably better voice."
    else:
        level, text = "low", "Add more recordings: at least 2 minutes of speech is needed to train."
    return {"files": len(files), "seconds": round(total, 1), "voiced_seconds": round(voiced, 1),
            "flagged": flagged, "level": level, "text": text,
            "min_seconds": DATASET_MIN_SECONDS, "good_seconds": DATASET_GOOD_SECONDS}


def dataset_file_out(f: DatasetFile) -> dict:
    return {"id": f.id, "filename": f.filename, "duration": f.duration,
            "analysis": f.analysis, "url": file_url(f.path)}


def voice_out(v: Voice, viewer: User, detail: bool = False) -> dict:
    mine = v.owner_id == viewer.id
    out = {
        "id": v.id, "name": v.name, "description": v.description,
        "status": v.status, "status_detail": v.status_detail if mine else "",
        "visibility": v.visibility, "source": v.source, "is_owner": mine,
        "owner_name": v.owner.display_name,
        "has_index": bool(v.index_path), "meta": v.meta or {},
        "created_at": v.created_at.isoformat(),
    }
    if mine:
        out["consent"] = {"type": v.consent_type, "name": v.consent_name,
                          "at": v.consent_at.isoformat(), "has_audio": bool(v.consent_audio)}
    if detail and mine:
        out["dataset"] = [dataset_file_out(f) for f in v.dataset]
        out["dataset_summary"] = dataset_summary(v.dataset)
    return out


OUTPUT_LABELS = {"output": "", "vocals": " (vocals)", "instrumental": " (instrumental)"}


def job_out(j: Job) -> dict:
    base = safe_name(j.title, "voicely")
    outputs = {}
    for name, rel in (j.outputs or {}).items():
        ext = rel.rsplit(".", 1)[-1]
        outputs[name] = {"url": file_url(rel),
                         "download_url": file_url(rel, f"{base}{OUTPUT_LABELS.get(name, ' ' + name)}.{ext}")}
    return {
        "id": j.id, "type": j.type, "title": j.title, "status": j.status,
        "progress": j.progress, "stage": j.stage, "error": j.error, "log": j.log,
        "voice_id": j.voice_id, "voice_name": j.voice_name,
        "params": j.params, "meta": j.meta, "outputs": outputs,
        "input_url": file_url(j.input_path),
        "created_at": j.created_at.isoformat(),
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "seconds": j.seconds,
    }
