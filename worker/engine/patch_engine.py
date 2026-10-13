"""Build-time fixes to the pinned RVC engine.

Usage: patch_engine.py <rvc dir>

Each patch asserts that its target text is present exactly once, so a changed
upstream commit fails the image build instead of silently shipping unpatched.
"""
import os
import sys

PATCHES = [
    # Pitch extraction for training hardcodes the GPU; fall back to CPU.
    (
        "extract_f0_print.py",
        'self.model_rmvpe = RMVPE("rmvpe.pt", is_half=False, device="cuda:0")',
        'self.model_rmvpe = RMVPE("rmvpe.pt", is_half=False, '
        'device="cuda:0" if torch.cuda.is_available() else "cpu")',
    ),
    # With no GPU, device_count() is 0 and the trainer spawns no process at
    # all, exiting "successfully" without training. Run one CPU process.
    (
        "train_nsf_sim_cache_sid_load_pretrain.py",
        "    if torch.cuda.is_available() == False and torch.backends.mps.is_available() == True:\n"
        "        n_gpus = 1\n",
        "    if n_gpus < 1:\n"
        "        n_gpus = 1\n",
    ),
]

# Base models live on a volume; the engine looks for them by relative path.
LINKS = {
    "hubert_base.pt": "/models/hubert_base.pt",
    "rmvpe.pt": "/models/rmvpe.pt",
    "pretrained_v2/f0G40k.pth": "/models/pretrained_v2/f0G40k.pth",
    "pretrained_v2/f0D40k.pth": "/models/pretrained_v2/f0D40k.pth",
}


def main() -> None:
    root = sys.argv[1]

    for rel, old, new in PATCHES:
        path = os.path.join(root, rel)
        text = open(path, encoding="utf-8").read()
        if text.count(old) != 1:
            sys.exit(f"patch target not found exactly once in {rel}")
        open(path, "w", encoding="utf-8").write(text.replace(old, new))
        print(f"patched {rel}")

    # The engine's audio loader and trainer read these files unconditionally.
    csvdb = os.path.join(root, "csvdb")
    os.makedirs(csvdb, exist_ok=True)
    open(os.path.join(csvdb, "formanting.csv"), "w").write("False,1.0,1.0\n")
    open(os.path.join(csvdb, "stop.csv"), "w").write("False\n")

    for rel, target in LINKS.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.lexists(path):
            os.remove(path)
        os.symlink(target, path)
        print(f"linked {rel} -> {target}")

    for d in ("logs", "weights"):
        os.makedirs(os.path.join(root, d), exist_ok=True)


if __name__ == "__main__":
    main()
