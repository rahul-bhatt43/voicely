"""Vocal / instrumental separation with a UVR MDX-Net model.

Same windowing and STFT layout as kae0-0/Colab-for-MDX_B (the separation code
verified in RVC_ARCHITECTURE.md), reduced to the single ONNX-model path and
streamed window by window so a full song does not have to fit in memory twice.
"""
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio
from .config import MDX_DENOISE, MDX_MODEL

SR = 44100

# Parameters for UVR-MDX-NET-Voc_FT, from the reference model_data.json.
N_FFT = 7680
HOP = 1024
DIM_F = 3072
DIM_T = 256
COMPENSATE = 1.021

CHUNK = HOP * (DIM_T - 1)
TRIM = N_FFT // 2
GEN = CHUNK - 2 * TRIM
N_BINS = N_FFT // 2 + 1


class Separator:
    def __init__(self, model_path: Path = MDX_MODEL):
        import onnxruntime as ort
        import torch

        self.torch = torch
        wanted = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        providers = [p for p in wanted if p in ort.get_available_providers()]
        self.session = ort.InferenceSession(str(model_path), providers=providers)
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        if list(inp.shape[1:]) != [4, DIM_F, DIM_T]:
            raise RuntimeError(f"unexpected separation model input shape {inp.shape}")
        self.window = torch.hann_window(N_FFT, periodic=True)

    def _stft(self, wave):
        torch = self.torch
        x = torch.stft(wave, n_fft=N_FFT, hop_length=HOP, window=self.window,
                       center=True, return_complex=True)
        x = torch.view_as_real(x).permute(0, 3, 1, 2)
        x = x.reshape(-1, 2, 2, N_BINS, DIM_T).reshape(-1, 4, N_BINS, DIM_T)
        return x[:, :, :DIM_F]

    def _istft(self, spec):
        torch = self.torch
        pad = torch.zeros(spec.shape[0], 4, N_BINS - DIM_F, DIM_T)
        x = torch.cat([spec, pad], dim=-2)
        x = x.reshape(-1, 2, 2, N_BINS, DIM_T).reshape(-1, 2, N_BINS, DIM_T)
        x = torch.view_as_complex(x.permute(0, 2, 3, 1).contiguous())
        x = torch.istft(x, n_fft=N_FFT, hop_length=HOP, window=self.window, center=True)
        return x.reshape(-1, 2, CHUNK)

    def _predict(self, spec: np.ndarray) -> np.ndarray:
        run = lambda s: self.session.run(None, {self.input_name: s})[0]  # noqa: E731
        if MDX_DENOISE:
            return run(spec) * 0.5 - run(-spec) * 0.5
        return run(spec)

    def separate(self, src: Path, vocals_out: Path, inst_out: Path,
                 progress: Callable[[float], None] = lambda p: None,
                 check_cancel: Callable[[], None] = lambda: None) -> None:
        import soundfile as sf
        torch = self.torch

        mix = audio.decode(src, SR, channels=2)
        n = mix.shape[1]
        pad = GEN - n % GEN
        padded = np.concatenate(
            [np.zeros((2, TRIM), np.float32), mix, np.zeros((2, pad + TRIM), np.float32)], axis=1)

        vocals = np.empty((2, n + pad), np.float32)
        starts = range(0, n + pad, GEN)
        for k, i in enumerate(starts):
            check_cancel()
            wave = torch.from_numpy(padded[:, i:i + CHUNK])
            with torch.no_grad():
                pred = self._predict(self._stft(wave).numpy())
                out = self._istft(torch.from_numpy(pred))
            vocals[:, i:i + GEN] = out[0, :, TRIM:-TRIM].numpy()
            progress((k + 1) / len(starts))

        vocals = vocals[:, :n] * COMPENSATE
        sf.write(str(vocals_out), vocals.T, SR, subtype="PCM_16")
        sf.write(str(inst_out), (mix - vocals).T, SR, subtype="PCM_16")
