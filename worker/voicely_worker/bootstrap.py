"""Download the shared base models into the models volume.

Runs as a one-shot compose service with internet access, so the worker itself
can stay on an internal-only network. Safe to re-run: complete files are kept.
"""
import os
import sys
import time
import urllib.request

from .config import MODELS_DIR

HF_RVC = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main"
HF_PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
UVR = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models"

# Voices offered for the text-to-voice flow: id -> (repo path, label).
PIPER_VOICES = {
    "en_US-lessac-medium": ("en/en_US/lessac/medium", "English (US) - Lessac, female"),
    "en_US-ryan-medium": ("en/en_US/ryan/medium", "English (US) - Ryan, male"),
    "en_GB-alba-medium": ("en/en_GB/alba/medium", "English (UK) - Alba, female"),
    "hi_IN-pratham-medium": ("hi/hi_IN/pratham/medium", "Hindi - Pratham, male"),
    "hi_IN-priyamvada-medium": ("hi/hi_IN/priyamvada/medium", "Hindi - Priyamvada, female"),
    "es_ES-davefx-medium": ("es/es_ES/davefx/medium", "Spanish - DaveFX, male"),
}


def manifest() -> list[tuple[str, str]]:
    """(relative path under MODELS_DIR, url) for every file the worker needs."""
    files = [
        ("hubert_base.pt", f"{HF_RVC}/hubert_base.pt"),
        ("rmvpe.pt", f"{HF_RVC}/rmvpe.pt"),
        ("pretrained_v2/f0G40k.pth", f"{HF_RVC}/pretrained_v2/f0G40k.pth"),
        ("pretrained_v2/f0D40k.pth", f"{HF_RVC}/pretrained_v2/f0D40k.pth"),
        ("mdx/UVR-MDX-NET-Voc_FT.onnx", f"{UVR}/UVR-MDX-NET-Voc_FT.onnx"),
    ]
    for vid, (path, _label) in PIPER_VOICES.items():
        files.append((f"piper/{vid}.onnx", f"{HF_PIPER}/{path}/{vid}.onnx"))
        files.append((f"piper/{vid}.onnx.json", f"{HF_PIPER}/{path}/{vid}.onnx.json"))
    return files


def missing() -> list[str]:
    return [rel for rel, _ in manifest() if not (MODELS_DIR / rel).is_file()]


def download(rel: str, url: str, attempts: int = 4) -> None:
    dest = MODELS_DIR / rel
    if dest.is_file():
        print(f"ok       {rel}", flush=True)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "voicely-bootstrap"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                done, last = 0, time.time()
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 5:
                        last = time.time()
                        pct = f"{done * 100 // total}%" if total else f"{done >> 20} MB"
                        print(f"  ...    {rel} {pct}", flush=True)
            if total and done != total:
                raise IOError(f"short download: {done} of {total} bytes")
            # Only a complete file ever gets the final name.
            os.replace(part, dest)
            print(f"fetched  {rel} ({done >> 20} MB)", flush=True)
            return
        except Exception as e:  # noqa: BLE001 - retry any network failure
            print(f"retry {attempt}/{attempts} {rel}: {e}", flush=True)
            time.sleep(3 * attempt)
    raise SystemExit(f"could not download {url}")


def main() -> None:
    print(f"Preparing base models in {MODELS_DIR}", flush=True)
    for rel, url in manifest():
        download(rel, url)
    print("All base models present.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
