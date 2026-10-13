"""Files on the shared data volume. All paths stored in the database are
relative to the data dir, which is also how the worker receives them."""
import json
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from .config import settings
from .security import file_token

AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".webm", ".mp4", ".wma", ".aiff", ".aif"}


def abs_path(rel: str) -> Path:
    root = settings.data_dir.resolve()
    p = (root / rel).resolve()
    if root not in p.parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return p


def file_url(rel: str | None, filename: str | None = None) -> str | None:
    return f"/api/files/{file_token(rel, filename)}" if rel else None


def safe_name(name: str, fallback: str = "audio") -> str:
    stem = re.sub(r"[^\w\- .()]+", "_", Path(name or "").stem).strip(" .")[:80]
    return stem or fallback


def audio_ext(upload: UploadFile) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"'{upload.filename}' is not a supported audio file.")
    return ext


def save_upload(upload: UploadFile, rel: str, max_mb: int) -> Path:
    """Stream an upload to disk, stopping as soon as it exceeds the limit."""
    dest = abs_path(rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    limit, size = max_mb * 1024 * 1024, 0
    try:
        with open(dest, "wb") as out:
            while chunk := upload.file.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        f"'{upload.filename}' is larger than {max_mb} MB.")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{upload.filename}' is empty.")
    return dest


def remove(rel: str | None) -> None:
    if not rel:
        return
    p = abs_path(rel)
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    else:
        p.unlink(missing_ok=True)


def probe_duration(path: Path) -> float:
    """Length in seconds, or 400 if ffprobe finds no audio in the file."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "format=duration:stream=codec_name", "-of", "json", str(path)],
        capture_output=True, timeout=60)
    try:
        info = json.loads(proc.stdout or b"{}")
        if not info.get("streams"):
            raise ValueError("no audio stream")
        return float(info["format"]["duration"])
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "That file could not be read as audio.") from None


def analyze_recording(path: Path) -> dict:
    """Measure a training recording and flag the problems that hurt a voice
    model most: clipping, low level, and long silences."""
    duration = probe_duration(path)
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-vn", "-af",
         "astats=measure_perchannel=none:measure_overall=Peak_level+RMS_level+Noise_floor+Peak_count,"
         "silencedetect=noise=-45dB:d=0.6", "-f", "null", "-"],
        capture_output=True, timeout=300)
    err = proc.stderr.decode("utf-8", "replace")

    def stat(label: str) -> float | None:
        m = re.search(rf"{label}:\s*(-?[\d.]+|-inf)", err)
        return None if not m or m.group(1) == "-inf" else float(m.group(1))

    peak, rms, floor = stat("Peak level dB"), stat("RMS level dB"), stat("Noise floor dB")
    # A normalized file touches full scale once or twice; a clipped one sits
    # there for many samples.
    clipped = peak is not None and peak >= -0.1 and (stat("Peak count") or 0) >= 25
    silence = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", err))
    voiced = max(0.0, duration - silence)

    issues = []
    if duration < 3:
        issues.append({"level": "warn", "text": "Very short. Clips under 3 seconds add little."})
    if clipped:
        issues.append({"level": "bad", "text": "Clipping: the recording is distorted at its loudest points. Re-record further from the mic or with lower gain."})
    if rms is not None and rms < -35:
        issues.append({"level": "warn", "text": "Very quiet. Record closer to the mic or raise the gain."})
    if floor is not None and floor > -50:
        issues.append({"level": "warn", "text": "Noticeable background noise. Find a quieter room or use a closer mic."})
    if duration > 5 and silence / duration > 0.5:
        issues.append({"level": "warn", "text": "More than half of this file is silence."})

    return {
        "duration": round(duration, 2),
        "voiced_seconds": round(voiced, 2),
        "peak_db": peak, "rms_db": rms, "noise_floor_db": floor,
        "issues": issues,
    }
