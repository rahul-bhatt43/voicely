"""ffmpeg helpers: decode, encode, mix. No engine imports here."""
import json
import subprocess
from pathlib import Path

import numpy as np

# Embedded in every output file so generated audio is labelled as such.
PROVENANCE = "AI-generated audio: voice converted with Voicely (RVC)"

FORMATS = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
}


class AudioError(Exception):
    """An input that ffmpeg could not handle; safe to show to the user."""


def run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise AudioError("ffmpeg failed: " + " | ".join(tail))
    return proc


def decode(path: Path, sr: int, channels: int = 1) -> np.ndarray:
    """Decode any audio file to float32. Mono -> (n,), stereo -> (2, n)."""
    proc = run([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
        "-vn", "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels), "-ar", str(sr), "-",
    ])
    audio = np.frombuffer(proc.stdout, np.float32)
    if audio.size == 0:
        raise AudioError("the file contains no audio")
    if channels == 1:
        return audio.copy()
    return audio.reshape(-1, channels).T.copy()


def duration(path: Path) -> float:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path),
    ])
    return float(json.loads(proc.stdout)["format"]["duration"])


def encode(src: Path, dst: Path, fmt: str, title: str | None = None) -> Path:
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-vn", *FORMATS[fmt],
           "-metadata", f"comment={PROVENANCE}"]
    if title:
        cmd += ["-metadata", f"title={title}"]
    run(cmd + [str(dst)])
    return dst


def has_filter(name: str) -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True).stdout.decode()
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


def mix(vocals: Path, instrumental: Path, dst: Path, *, vocal_gain_db: float = 0.0,
        inst_gain_db: float = 0.0, reverb: float = 0.0, inst_semitones: int = 0) -> Path:
    """Mix a converted vocal with an instrumental into a 44.1 kHz stereo WAV.

    reverb is 0..1 (wet level of a short echo-based room). inst_semitones
    transposes the instrumental so it stays in key with a shifted vocal.
    """
    v = f"[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={vocal_gain_db}dB"
    if reverb > 0:
        wet = round(min(reverb, 1.0) * 0.6, 3)
        v += (f",asplit[dry][w0];[w0]aecho=0.8:0.8:45|90|140:0.4|0.28|0.18,volume={wet}[wet];"
              "[dry][wet]amix=inputs=2:normalize=0[v]")
    else:
        v += "[v]"

    i = "[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"
    if inst_semitones:
        ratio = 2 ** (inst_semitones / 12)
        if has_filter("rubberband"):
            i += f",rubberband=pitch={ratio:.6f}"
        else:
            # Resample to shift pitch, then restore the tempo.
            i += f",asetrate={int(44100 * ratio)},aresample=44100,atempo={1 / ratio:.6f}"
    i += f",volume={inst_gain_db}dB[i]"

    graph = f"{v};{i};[v][i]amix=inputs=2:normalize=0,alimiter=limit=0.97[out]"
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(vocals), "-i", str(instrumental),
         "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", str(dst)])
    return dst
