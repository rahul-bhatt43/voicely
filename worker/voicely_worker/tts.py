"""Text to speech with Piper, for the text-in-a-custom-voice flow.

Piper only produces the *performance* (words, timing, intonation); RVC then
re-renders it in the target voice.
"""
import subprocess
from pathlib import Path

from .bootstrap import PIPER_VOICES
from .config import PIPER_BIN, PIPER_DIR


class TTSError(Exception):
    pass


def synthesize(text: str, voice: str, dst_wav: Path, speed: float = 1.0) -> Path:
    if voice not in PIPER_VOICES:
        raise TTSError(f"Unknown narrator voice: {voice}")
    model = PIPER_DIR / f"{voice}.onnx"
    if not model.is_file():
        raise TTSError(f"Narrator voice {voice} is not installed on this worker.")

    # length_scale stretches phoneme durations, so it is the inverse of speed.
    proc = subprocess.run(
        [PIPER_BIN, "--model", str(model), "--output_file", str(dst_wav),
         "--length_scale", f"{1 / max(0.5, min(speed, 2.0)):.3f}"],
        input=text.encode("utf-8"), capture_output=True, timeout=900,
    )
    if proc.returncode != 0 or not dst_wav.is_file():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-2:]
        raise TTSError("Speech generation failed: " + " | ".join(tail))
    return dst_wav
