"""Turn the fork's requirements.txt into the set that actually installs.

Usage: make_requirements.py <fork requirements.txt> <cpu|cuda>

The edits are the ones listed in RVC_ARCHITECTURE.md section 4, plus the
worker's own queue client and an optional CPU-only torch build.
"""
import re
import sys

REMOVED = {"torchgen", "pathlib", "pyreadline3", "pysimplegui", "sounddevice"}
REPLACED = {"ffmpy": "ffmpy==0.3.1"}
# redis 4.5.5 is the newest client that accepts the fork's async-timeout pin.
ADDED = ["setuptools==69.5.1", "redis==4.5.5"]

CPU_OVERRIDES = {
    "torch": "torch==2.0.0+cpu",
    "torchaudio": "torchaudio==2.0.1+cpu",
    "onnxruntime-gpu": "onnxruntime==1.14.1",
}


def main() -> None:
    path, device = sys.argv[1], sys.argv[2]
    if device not in ("cpu", "cuda"):
        sys.exit(f"ENGINE_DEVICE must be cpu or cuda, got {device!r}")

    out = []
    if device == "cpu":
        out.append("--extra-index-url https://download.pytorch.org/whl/cpu")

    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[=<>!~\[ ]", line, maxsplit=1)[0].lower()
        if name in REMOVED:
            continue
        if name in REPLACED:
            line = REPLACED[name]
        elif device == "cpu" and name in CPU_OVERRIDES:
            line = CPU_OVERRIDES[name]
        out.append(line)

    out.extend(ADDED)
    print("\n".join(out))


if __name__ == "__main__":
    main()
