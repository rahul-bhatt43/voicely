"""Generate the Colab training notebook that the web app hands out.

    python tools/build_colab_notebook.py

The notebook embeds the worker's own training code (engine pin, requirement
fix-ups, patches, train.py), so a voice trained on Colab goes through exactly
the pipeline the server uses. Re-run this after changing any of those files.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "voicely-train-colab.ipynb"

EMBED = {
    "/content/voicely/make_requirements.py": "worker/engine/make_requirements.py",
    "/content/voicely/patch_engine.py": "worker/engine/patch_engine.py",
    "/content/voicely_worker/config.py": "worker/voicely_worker/config.py",
    "/content/voicely_worker/train.py": "worker/voicely_worker/train.py",
}

RVC_COMMIT = re.search(r"ARG RVC_COMMIT=(\w+)", (ROOT / "worker/Dockerfile").read_text()).group(1)
HF = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text: str, title: str | None = None) -> dict:
    meta = {"cellView": "form"} if title else {}
    src = (f"#@title {title}\n" if title else "") + text.strip("\n")
    return {"cell_type": "code", "metadata": meta, "execution_count": None, "outputs": [], "source": src}


def write_files_cell() -> str:
    lines = ["import os", "FILES = {}"]
    for dest, src in EMBED.items():
        lines.append(f"FILES[{dest!r}] = {(ROOT / src).read_text(encoding='utf-8')!r}")
    lines += [
        "FILES['/content/voicely_worker/__init__.py'] = ''",
        "for path, text in FILES.items():",
        "    os.makedirs(os.path.dirname(path), exist_ok=True)",
        "    open(path, 'w', encoding='utf-8').write(text)",
        "print('Wrote', len(FILES), 'Voicely training files.')",
    ]
    return "\n".join(lines)


SETTINGS = '''
VOICE_NAME = "my-voice"  #@param {type:"string"}
EPOCHS = 200  #@param {type:"slider", min:10, max:600, step:10}
BATCH_SIZE = 8  #@param {type:"slider", min:1, max:16, step:1}

import re, subprocess
VOICE_NAME = re.sub(r"[^\\w\\-]+", "_", VOICE_NAME).strip("_") or "my-voice"
HAS_GPU = subprocess.run("nvidia-smi", shell=True, capture_output=True).returncode == 0
DEVICE = "cuda" if HAS_GPU else "cpu"
if HAS_GPU:
    print(subprocess.run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", shell=True, capture_output=True, text=True).stdout.strip())
    print(f"GPU found. Training '{VOICE_NAME}' for {EPOCHS} epochs, batch size {BATCH_SIZE}.")
else:
    print("NO GPU. Go to Runtime > Change runtime type, pick T4 GPU, then run this cell again.")
    print("(Training on CPU works but takes many hours.)")
'''

INSTALL = f'''
import os, subprocess, sys

def sh(cmd):
    print("$", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)

if not os.path.isdir("/content/rvc/lib"):
    sh("rm -rf /content/rvc && git init -q /content/rvc")
    sh("cd /content/rvc && git remote add origin https://github.com/Mangio621/Mangio-RVC-Fork"
       " && git fetch -q --depth 1 origin {RVC_COMMIT} && git checkout -q FETCH_HEAD")

if subprocess.run("which ffmpeg", shell=True, capture_output=True).returncode != 0:
    sh("apt-get -qq update && apt-get -qq install -y ffmpeg")

# The engine needs Python 3.10 and 2023 package versions, so it gets its own
# environment instead of Colab's.
if not os.path.exists("/content/rvc-env/bin/python"):
    sh(f"{{sys.executable}} -m pip -q install uv")
    sh(f"{{sys.executable}} /content/voicely/make_requirements.py /content/rvc/requirements.txt {{DEVICE}} > /content/voicely/requirements.txt")
    sh("uv venv -q /content/rvc-env --python 3.10")
    sh("uv pip install -q --python /content/rvc-env/bin/python --index-strategy unsafe-best-match -r /content/voicely/requirements.txt")

os.makedirs("/models/pretrained_v2", exist_ok=True)
for name in ["hubert_base.pt", "rmvpe.pt", "pretrained_v2/f0G40k.pth", "pretrained_v2/f0D40k.pth"]:
    if not os.path.exists(f"/models/{{name}}"):
        sh(f"curl -fL --retry 4 -s -o /models/{{name}}.part {HF}/{{name}} && mv /models/{{name}}.part /models/{{name}}")

if not os.path.exists("/content/rvc/csvdb/stop.csv"):
    sh(f"{{sys.executable}} /content/voicely/patch_engine.py /content/rvc")
print("\\nEngine installed.")
'''

DATASET = '''
import os, shutil, zipfile, glob

AUDIO = (".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".webm", ".mp4")
ZIP = "/content/dataset.zip"

if not os.path.exists(ZIP):
    from google.colab import files
    print("Choose the recordings .zip you downloaded from Voicely.")
    uploaded = files.upload()
    if not uploaded:
        raise SystemExit("No file was uploaded.")
    os.rename(next(iter(uploaded)), ZIP)

shutil.rmtree("/content/dataset", ignore_errors=True)
shutil.rmtree("/content/dataset_raw", ignore_errors=True)
os.makedirs("/content/dataset")
with zipfile.ZipFile(ZIP) as z:
    z.extractall("/content/dataset_raw")
# Flatten: the trainer reads one folder and nothing but audio.
n = 0
for path in sorted(glob.glob("/content/dataset_raw/**/*", recursive=True)):
    if os.path.isfile(path) and path.lower().endswith(AUDIO):
        n += 1
        shutil.move(path, f"/content/dataset/{n:04d}{os.path.splitext(path)[1].lower()}")
shutil.rmtree("/content/dataset_raw")
if n == 0:
    raise SystemExit("The zip contains no audio files.")
print(f"{n} recordings ready.")
'''

RUNNER = '''
import os, sys, time
from pathlib import Path
os.environ["DATA_DIR"] = "/content/voicely-data"
os.environ["RVC_DIR"] = "/content/rvc"
sys.path.insert(0, "/content")
import torch
from voicely_worker import train

state = {"stage": None, "log": ""}
def emit(**f):
    state["log"] = f.get("log", state["log"])
    stage = f.get("stage")
    if stage and stage != state["stage"]:
        state["stage"] = stage
        print(f"[{time.strftime('%H:%M:%S')}] {round(f.get('progress', 0) * 100):3d}%  {stage}", flush=True)

try:
    meta = train.train(
        "colab", Path("/content/dataset"), Path("/content/voice"),
        {"epochs": int(sys.argv[1]), "batch_size": int(sys.argv[2])},
        gpu=torch.cuda.is_available(), emit=emit, is_canceled=lambda: False)
except train.TrainError as e:
    print("\\n--- engine output ---\\n" + state["log"][-3000:])
    sys.exit(f"TRAINING FAILED: {e}")
print("TRAINING DONE:", meta)
'''

TRAIN = f'''
import subprocess
open("/content/voicely/run_training.py", "w").write({RUNNER!r})
print("Training starts. The percentage moves once per epoch; keep this tab open.\\n")
r = subprocess.run(["/content/rvc-env/bin/python", "/content/voicely/run_training.py", str(EPOCHS), str(BATCH_SIZE)])
if r.returncode != 0:
    raise SystemExit("Training did not finish. Read the messages above.")
'''

PACKAGE = '''
import os, zipfile
out = f"/content/{VOICE_NAME}-voicely.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
    z.write("/content/voice/model.pth", f"{VOICE_NAME}.pth")
    z.write("/content/voice/model.index", f"added_{VOICE_NAME}.index")
print(f"Saved {out} ({os.path.getsize(out) / 1e6:.0f} MB)")
try:
    from google.colab import files
    files.download(out)
    print("Your browser is downloading it. In Voicely: open the voice > Import a trained model > choose this zip.")
except ImportError:
    pass
'''


def main() -> None:
    cells = [
        md("""
# Train a Voicely voice on a free GPU

This notebook trains a voice from the recordings you collected in Voicely and gives you back one
`.zip` to import.

1. **Runtime → Change runtime type → T4 GPU → Save.**
2. **Runtime → Run all.** When step 3 asks, choose the recordings `.zip` you downloaded from Voicely.
3. Wait. When it finishes, your browser downloads `<name>-voicely.zip`.
4. In Voicely, open the voice, choose **Import a trained model**, and pick that zip.

Keep this tab open while it runs. Free Colab sessions stop when idle and after a few hours, so for
a long dataset start with 200 epochs rather than the maximum.

Only train a voice that is your own or that you have clear permission to clone.
"""),
        code(SETTINGS, "1. Settings"),
        code(write_files_cell() + "\n" + INSTALL, "2. Install the voice engine (about 5 minutes)"),
        code(DATASET, "3. Upload your recordings"),
        code(TRAIN, "4. Train"),
        code(PACKAGE, "5. Download the voice"),
    ]
    nb = {
        "nbformat": 4, "nbformat_minor": 0,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4"},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    OUT.write_text(json.dumps(nb, indent=1), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB, engine {RVC_COMMIT[:8]})")


if __name__ == "__main__":
    main()
