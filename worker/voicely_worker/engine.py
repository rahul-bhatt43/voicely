"""Headless wrapper around the pinned RVC engine.

Calls VC.pipeline directly, the way the fork's GUI does, but without gradio,
without the fork's Config (which rewrites files on import) and without its
audio loader (which depends on a CSV in the working directory).
"""
import gc
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio
from .config import CHUNK_SECONDS, MODELS_DIR, RVC_DIR, VOICE_CACHE_SIZE

F0_METHODS = ("rmvpe", "harvest", "pm", "crepe", "mangio-crepe")
SR_IN = 16000  # HuBERT input rate
WINDOW = 160   # samples per pitch frame at 16 kHz


class ModelError(Exception):
    """A voice model that cannot be used; the message is safe to show the user."""


class _DeviceConfig:
    """The few fields VC reads from the fork's Config."""

    def __init__(self, torch):
        self.device = "cpu"
        self.is_half = False
        self.gpu_name = None
        if torch.cuda.is_available():
            self.device = "cuda:0"
            self.gpu_name = torch.cuda.get_device_name(0)
            name = self.gpu_name.upper()
            # Same cards the fork forces to full precision.
            no_half = ("16" in name and "V100" not in name) or any(
                k in name for k in ("P40", "1060", "1070", "1080"))
            self.is_half = not no_half
        if self.is_half:
            self.x_pad, self.x_query, self.x_center, self.x_max = 3, 10, 60, 65
        else:
            self.x_pad, self.x_query, self.x_center, self.x_max = 1, 6, 38, 41


def split_points(x: np.ndarray, sr: int, target: int, search: int = 4) -> list[int]:
    """Cut points roughly every `target` seconds, placed at the quietest moment
    nearby and aligned to the pitch frame size so chunks rejoin without drift."""
    points, pos, win = [], target * sr, sr // 50
    while len(x) - pos > 10 * sr:
        lo = pos - search * sr
        env = np.convolve(np.abs(x[lo:pos + search * sr]), np.ones(win) / win, mode="same")
        cut = (lo + int(np.argmin(env))) // WINDOW * WINDOW
        points.append(cut)
        pos = cut + target * sr
    return points


class Engine:
    def __init__(self):
        # The engine resolves hubert_base.pt, rmvpe.pt and its own modules
        # relative to the working directory.
        os.chdir(RVC_DIR)
        if str(RVC_DIR) not in sys.path:
            sys.path.insert(0, str(RVC_DIR))

        import torch
        self.torch = torch
        self.config = _DeviceConfig(torch)
        self.device = self.config.device
        self._hubert = None
        self._rmvpe = None
        self._voices: OrderedDict = OrderedDict()

    # -- shared base models -------------------------------------------------

    def _load_hubert(self):
        if self._hubert is None:
            from fairseq import checkpoint_utils
            models, _, _ = checkpoint_utils.load_model_ensemble_and_task(
                [str(MODELS_DIR / "hubert_base.pt")], suffix="")
            model = models[0].to(self.device)
            self._hubert = (model.half() if self.config.is_half else model.float()).eval()
        return self._hubert

    def _load_rmvpe(self):
        if self._rmvpe is None:
            from rmvpe import RMVPE
            self._rmvpe = RMVPE(str(MODELS_DIR / "rmvpe.pt"),
                                is_half=self.config.is_half, device=self.device)
        return self._rmvpe

    # -- voice models -------------------------------------------------------

    def read_checkpoint(self, path: Path) -> dict:
        """Load a voice .pth without executing pickled code.

        A real RVC voice holds only tensors and plain values, so the
        restricted unpickler accepts it; anything else is rejected.
        """
        name = path.name
        try:
            cpt = self.torch.load(str(path), map_location="cpu", weights_only=True)
        except Exception as e:  # noqa: BLE001
            raise ModelError(
                "This file could not be loaded as a voice model. It may be corrupt, "
                "or contain something other than model weights.") from e

        if not isinstance(cpt, dict) or "weight" not in cpt or "config" not in cpt:
            if isinstance(cpt, dict) and "model" in cpt:
                raise ModelError(
                    "This is a training checkpoint (G_*.pth / D_*.pth), not a finished voice. "
                    "Upload the small file from the 'weights' folder instead.")
            raise ModelError("This .pth is not an RVC voice model.")
        if "emb_g.weight" not in cpt["weight"] or len(cpt["config"]) < 18:
            raise ModelError(f"{name} has an unexpected layout and cannot be used.")
        return cpt

    def inspect(self, model_path: Path, index_path: Path | None = None) -> dict:
        cpt = self.read_checkpoint(model_path)
        version = cpt.get("version", "v1")
        meta = {
            "sample_rate": int(cpt["config"][-1]),
            "version": version,
            "f0": int(cpt.get("f0", 1)),
            "info": str(cpt.get("info", ""))[:80],
        }
        if index_path is not None:
            import faiss
            try:
                index = faiss.read_index(str(index_path))
            except Exception as e:  # noqa: BLE001
                raise ModelError("The index file could not be read by FAISS.") from e
            want = 256 if version == "v1" else 768
            if index.d != want:
                raise ModelError(
                    f"The index does not match this model (index has {index.d} dimensions, "
                    f"a {version} model needs {want}). Use the 'added_*.index' trained with it.")
            meta["index_vectors"] = int(index.ntotal)
        return meta

    def _load_voice(self, path: Path):
        key = (str(path), path.stat().st_mtime_ns)
        if key in self._voices:
            self._voices.move_to_end(key)
            return self._voices[key]

        from lib.infer_pack.models import (
            SynthesizerTrnMs256NSFsid, SynthesizerTrnMs256NSFsid_nono,
            SynthesizerTrnMs768NSFsid, SynthesizerTrnMs768NSFsid_nono,
        )
        from vc_infer_pipeline import VC

        cpt = self.read_checkpoint(path)
        tgt_sr = int(cpt["config"][-1])
        cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]  # speaker count
        if_f0 = int(cpt.get("f0", 1))
        version = cpt.get("version", "v1")
        half = self.config.is_half

        if version == "v1":
            net = (SynthesizerTrnMs256NSFsid(*cpt["config"], is_half=half) if if_f0
                   else SynthesizerTrnMs256NSFsid_nono(*cpt["config"]))
        else:
            net = (SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=half) if if_f0
                   else SynthesizerTrnMs768NSFsid_nono(*cpt["config"]))
        del net.enc_q
        net.load_state_dict(cpt["weight"], strict=False)
        net.eval().to(self.device)
        net = net.half() if half else net.float()

        vc = VC(tgt_sr, self.config)
        voice = (net, vc, tgt_sr, if_f0, version)
        self._voices[key] = voice
        while len(self._voices) > VOICE_CACHE_SIZE:
            self._voices.popitem(last=False)
            self._free()
        return voice

    def _free(self):
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()

    # -- conversion ---------------------------------------------------------

    def convert(self, src: Path, dst_wav: Path, model: Path, index: Path | None, params: dict,
                progress: Callable[[float], None] = lambda p: None,
                check_cancel: Callable[[], None] = lambda: None) -> dict:
        """Convert src into the voice at `model`, writing a mono 16-bit WAV."""
        import vc_infer_pipeline
        from scipy.io import wavfile

        f0_method = params.get("f0_method", "rmvpe")
        if f0_method not in F0_METHODS:
            raise ModelError(f"Unknown pitch method: {f0_method}")
        resample_sr = int(params.get("resample_sr", 0))

        x = audio.decode(src, SR_IN)
        if len(x) < SR_IN // 2:
            raise audio.AudioError("the audio is too short to convert (under half a second)")
        peak = np.abs(x).max() / 0.95
        if peak > 1:
            x = x / peak

        net, vc, tgt_sr, if_f0, version = self._load_voice(model)
        hubert = self._load_hubert()
        if if_f0 and f0_method == "rmvpe":
            vc.model_rmvpe = self._load_rmvpe()  # share one copy across voices

        out_sr = resample_sr if resample_sr >= 16000 and resample_sr != tgt_sr else tgt_sr
        bounds = [0, *split_points(x, SR_IN, CHUNK_SECONDS), len(x)]
        times = [0.0, 0.0, 0.0]
        out = []
        try:
            for n, (a, b) in enumerate(zip(bounds, bounds[1:])):
                check_cancel()
                seg = vc.pipeline(
                    hubert, net, 0, x[a:b].copy(), f"{src}#{n}", times,
                    int(params.get("pitch", 0)), f0_method,
                    str(index) if index else "", float(params.get("index_rate", 0.66)),
                    if_f0, int(params.get("filter_radius", 3)), tgt_sr, resample_sr,
                    float(params.get("rms_mix_rate", 0.21)), version,
                    float(params.get("protect", 0.33)), int(params.get("crepe_hop_length", 120)),
                )
                # The engine returns each call a few frames short. Left alone
                # that adds up, and a cover's vocal drifts ahead of the music.
                want = round((b - a) * out_sr / SR_IN)
                out.append(np.pad(seg, (0, max(0, want - len(seg))))[:want])
                progress((n + 1) / (len(bounds) - 1))
        finally:
            # The harvest path caches whole input arrays by name; drop them.
            vc_infer_pipeline.input_audio_path2wav.clear()
            vc_infer_pipeline.cache_harvest_f0.cache_clear()
            self._free()

        wavfile.write(str(dst_wav), out_sr, np.concatenate(out))
        return {
            "sample_rate": out_sr,
            "seconds": round(len(x) / SR_IN, 2),
            "timing": {"features": round(times[0], 2), "pitch": round(times[1], 2),
                       "synthesis": round(times[2], 2)},
        }
