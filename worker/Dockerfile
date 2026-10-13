# syntax=docker/dockerfile:1.7
#
# Voicely worker: the pinned 2023 RVC runtime behind a Redis job queue.
# Everything here is frozen on purpose (see RVC_ARCHITECTURE.md section 4) -
# do not bump Python or the engine pins without re-verifying conversion.
FROM ubuntu:22.04

# cpu  -> torch 2.0.0+cpu, onnxruntime           (small image, no NVIDIA libs)
# cuda -> torch 2.0.0 (CUDA 11.7), onnxruntime-gpu (about 5 GB of packages)
ARG ENGINE_DEVICE=cpu
ARG RVC_COMMIT=bf0ffdbc35da09b57306e429c6deda84496948a1
ARG PIPER_VERSION=2023.11.14-2

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-dev python3.10-venv build-essential \
        git curl ca-certificates ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# RVC engine, pinned by commit.
RUN git init -q /opt/rvc && cd /opt/rvc \
    && git remote add origin https://github.com/Mangio621/Mangio-RVC-Fork \
    && git fetch -q --depth 1 origin ${RVC_COMMIT} \
    && git checkout -q FETCH_HEAD \
    && rm -rf .git *.exe *.lib *.bat *.ipynb docs

# Python environment: the fork's own pins with the documented fixes applied.
COPY engine/make_requirements.py /build/make_requirements.py
RUN python3.10 /build/make_requirements.py /opt/rvc/requirements.txt ${ENGINE_DEVICE} > /build/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv --python /usr/bin/python3.10 \
    && uv pip install --python /opt/venv/bin/python \
        --index-strategy unsafe-best-match -r /build/requirements.txt

# Piper: a self-contained TTS binary, so it cannot disturb the pinned env.
RUN curl -fsSL https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz \
    | tar -xz -C /opt

# Engine fixes needed to run headless and on CPU. Fails the build if the
# upstream code no longer matches what the patches expect.
COPY engine/patch_engine.py /build/patch_engine.py
RUN python3.10 /build/patch_engine.py /opt/rvc

# Unprivileged user: voice models are untrusted input.
RUN useradd --uid 1000 --create-home voicely \
    && mkdir -p /data /models /app \
    && chown -R voicely:voicely /opt/rvc /data /models /app

COPY --chown=voicely:voicely voicely_worker /app/voicely_worker

USER voicely
WORKDIR /app
ENV PYTHONPATH=/app \
    RVC_DIR=/opt/rvc \
    DATA_DIR=/data \
    MODELS_DIR=/models \
    PIPER_BIN=/opt/piper/piper \
    HOME=/home/voicely

CMD ["python", "-m", "voicely_worker.main"]
