"""Train a custom voice from a folder of recordings.

Drives the fork's own scripts as subprocesses, in the order its GUI does:
slice -> pitch -> HuBERT features -> fine-tune -> FAISS index. The scripts
swallow their own errors and exit 0, so every step is checked by its output.
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from random import shuffle
from typing import Callable

import numpy as np

from .config import DATA_DIR, RVC_DIR

SR_NAME, SR_HZ, VERSION, FEAT_DIM = "40k", 40000, "v2", 768
EPOCH_RE = re.compile(r"====> Epoch: (\d+)")


class TrainError(Exception):
    """A training failure whose message is safe to show the user."""


class Canceled(Exception):
    pass


def _run(cmd: list[str], log: Path, is_canceled: Callable[[], bool],
         tick: Callable[[], None] = lambda: None) -> None:
    """Run an engine script to completion, appending its output to `log`."""
    with open(log, "ab") as out:
        out.write(f"\n$ {' '.join(cmd)}\n".encode())
        out.flush()
        proc = subprocess.Popen(cmd, cwd=RVC_DIR, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            while proc.poll() is None:
                if is_canceled():
                    raise Canceled()
                tick()
                time.sleep(2)
        finally:
            if proc.poll() is None:
                # The trainer spawns children; take down the whole group.
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()


def _tail(path: Path, limit: int = 3000) -> str:
    if not path.is_file():
        return ""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - limit))
        return f.read().decode("utf-8", "replace")


def _count(d: Path, suffix: str) -> int:
    return len([p for p in d.glob(f"*{suffix}")]) if d.is_dir() else 0


def build_index(feature_dir: Path, dst: Path) -> int:
    """Build the retrieval index the same way the fork's train_index does."""
    import faiss

    feats = np.concatenate([np.load(p) for p in sorted(feature_dir.glob("*.npy"))], 0)
    order = np.arange(feats.shape[0])
    np.random.shuffle(order)
    feats = feats[order]
    if feats.shape[0] > 2e5:
        from sklearn.cluster import MiniBatchKMeans
        feats = MiniBatchKMeans(n_clusters=10000, batch_size=256 * (os.cpu_count() or 1),
                                compute_labels=False, init="random").fit(feats).cluster_centers_
    feats = np.ascontiguousarray(feats, dtype=np.float32)

    n_ivf = max(1, min(int(16 * np.sqrt(feats.shape[0])), feats.shape[0] // 39))
    index = faiss.index_factory(FEAT_DIM, f"IVF{n_ivf},Flat")
    faiss.extract_index_ivf(index).nprobe = 1
    index.train(feats)
    for i in range(0, feats.shape[0], 8192):
        index.add(feats[i:i + 8192])
    faiss.write_index(index, str(dst))
    return int(index.ntotal)


def train(job_id: str, dataset_dir: Path, voice_dir: Path, params: dict, *, gpu: bool,
          emit: Callable[..., None], is_canceled: Callable[[], bool]) -> dict:
    epochs = int(params.get("epochs", 200))
    batch_size = int(params.get("batch_size", 8 if gpu else 4))
    py = sys.executable

    exp = "v" + job_id.replace("-", "")[:20]
    work = DATA_DIR / "work" / "train" / exp
    link = RVC_DIR / "logs" / exp       # the scripts only look under logs/
    weight = RVC_DIR / "weights" / f"{exp}.pth"
    log = work / "voicely.log"
    exp_dir = str(link)

    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(work, target_is_directory=True)

    try:
        cpus = min(os.cpu_count() or 1, 8)

        emit(stage="Slicing recordings", progress=0.01)
        _run([py, "trainset_preprocess_pipeline_print.py", str(dataset_dir), str(SR_HZ),
              str(cpus), exp_dir, "False"], log, is_canceled)
        clips = _count(work / "0_gt_wavs", ".wav")
        if clips < 8:
            raise TrainError(
                f"Only {clips} usable clips were found after removing silence. "
                "Add more clean recordings (aim for at least 10 minutes).")

        emit(stage=f"Extracting pitch ({clips} clips)", progress=0.05)
        _run([py, "extract_f0_print.py", exp_dir, "1" if gpu else str(min(cpus, 2)), "rmvpe", "128"],
             log, is_canceled)
        if _count(work / "2a_f0", ".npy") == 0:
            raise TrainError("Pitch extraction produced no output. See the training log.")

        emit(stage="Extracting voice features", progress=0.12)
        feature_cmd = [py, "extract_feature_print.py", "cuda:0" if gpu else "cpu", "1", "0"]
        feature_cmd += ["0"] if gpu else []
        _run(feature_cmd + [exp_dir, VERSION], log, is_canceled)
        feature_dir = work / f"3_feature{FEAT_DIM}"
        if _count(feature_dir, ".npy") == 0:
            raise TrainError("Feature extraction produced no output. See the training log.")

        # Clips that made it through every stage, plus the fork's two silent
        # reference rows.
        stem = lambda d, suffix: {p.name[:-len(suffix)] for p in (work / d).glob(f"*{suffix}")}  # noqa: E731
        names = (stem("0_gt_wavs", ".wav") & stem(feature_dir.name, ".npy")
                 & stem("2a_f0", ".wav.npy") & stem("2b-f0nsf", ".wav.npy"))
        if len(names) < batch_size:
            raise TrainError("Too few clips survived preprocessing to train on.")
        rows = [f"{exp_dir}/0_gt_wavs/{n}.wav|{exp_dir}/{feature_dir.name}/{n}.npy|"
                f"{exp_dir}/2a_f0/{n}.wav.npy|{exp_dir}/2b-f0nsf/{n}.wav.npy|0" for n in names]
        mute = f"{RVC_DIR}/logs/mute"
        rows += [f"{mute}/0_gt_wavs/mute{SR_NAME}.wav|{mute}/3_feature{FEAT_DIM}/mute.npy|"
                 f"{mute}/2a_f0/mute.wav.npy|{mute}/2b-f0nsf/mute.wav.npy|0"] * 2
        shuffle(rows)
        (work / "filelist.txt").write_text("\n".join(rows))

        steps = -(-len(names) // batch_size)
        log_interval = steps + 1 if steps > 1 else 1

        def report():
            done = [int(m) for m in EPOCH_RE.findall(_tail(work / "train.log", 20000))]
            epoch = max(done, default=0)
            emit(stage=f"Training - epoch {min(epoch + 1, epochs)} of {epochs}",
                 progress=0.2 + 0.74 * epoch / epochs, log=_tail(work / "train.log"))

        emit(stage=f"Training - epoch 1 of {epochs}", progress=0.2)
        weight.unlink(missing_ok=True)
        _run([py, "train_nsf_sim_cache_sid_load_pretrain.py", "-e", exp, "-sr", SR_NAME,
              "-f0", "1", "-bs", str(batch_size), "-g", "0", "-te", str(epochs),
              "-se", str(epochs),  # no resume support, so skip mid-run checkpoints
              "-pg", "pretrained_v2/f0G40k.pth", "-pd", "pretrained_v2/f0D40k.pth",
              "-l", "1", "-c", "0", "-sw", "0", "-v", VERSION, "-li", str(log_interval)],
             log, is_canceled, tick=report)
        if not weight.is_file():
            raise TrainError("Training stopped before producing a voice model. "
                             "The usual cause is running out of memory; see the training log.")

        emit(stage="Building retrieval index", progress=0.95, log=_tail(work / "train.log"))
        voice_dir.mkdir(parents=True, exist_ok=True)
        vectors = build_index(feature_dir, voice_dir / "model.index")
        shutil.move(str(weight), voice_dir / "model.pth")

        return {"sample_rate": SR_HZ, "version": VERSION, "f0": 1, "epochs": epochs,
                "clips": len(names), "index_vectors": vectors}
    except TrainError:
        # Keep the engine's own output next to the message for diagnosis.
        emit(log=_tail(log, 4000))
        raise
    finally:
        weight.unlink(missing_ok=True)
        if link.is_symlink():
            link.unlink()
        shutil.rmtree(work, ignore_errors=True)
