"""Voicely worker: pulls jobs from Redis and reports back with events.

The worker never touches the database. It reads a job message, works on files
under DATA_DIR, and pushes status events that the API applies. That keeps the
process that loads untrusted voice models away from credentials and user data
it has no business reading.
"""
import json
import logging
import shutil
import socket
import threading
import time
import traceback
from pathlib import Path

import redis

from . import audio, bootstrap, train as training, tts
from .config import (CANCEL_PREFIX, EVENTS_KEY, MAX_RSS_MB, QUEUE_PREFIX, REDIS_URL,
                     WORKER_PREFIX, WORKER_QUEUES, data_path)
from .engine import Engine, ModelError

log = logging.getLogger("voicely.worker")

# Errors whose text was written for the user. Anything else is reported
# generically and logged in full here.
USER_ERRORS = (audio.AudioError, ModelError, tts.TTSError, training.TrainError)


class Canceled(Exception):
    pass


def rss_mb() -> int:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) // 1024
    return 0


class Worker:
    def __init__(self):
        self.redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        self.name = socket.gethostname()
        self.engine: Engine | None = None
        self.current: str | None = None
        self._last_progress = 0.0

    # -- reporting ----------------------------------------------------------

    def emit(self, job_id: str, **fields) -> None:
        self.redis.lpush(EVENTS_KEY, json.dumps({"job_id": job_id, "ts": time.time(), **fields}))

    def progress(self, job_id: str, value: float, stage: str | None = None) -> None:
        """Progress updates, limited to about one a second."""
        now = time.time()
        if stage is None and now - self._last_progress < 1.0 and value < 1.0:
            return
        self._last_progress = now
        fields = {"progress": round(min(max(value, 0.0), 1.0), 4)}
        if stage:
            fields["stage"] = stage
        self.emit(job_id, **fields)

    def is_canceled(self, job_id: str) -> bool:
        return bool(self.redis.exists(CANCEL_PREFIX + job_id))

    def check_cancel(self, job_id: str) -> None:
        if self.is_canceled(job_id):
            raise Canceled()

    def heartbeat(self) -> None:
        """Advertise this worker and keep the running job marked alive."""
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        while True:
            try:
                info = {
                    "name": self.name,
                    "queues": WORKER_QUEUES,
                    "device": self.engine.device if self.engine else None,
                    "gpu": self.engine.config.gpu_name if self.engine else None,
                    "busy": self.current,
                    "missing_models": bootstrap.missing(),
                    "tts_voices": [{"id": k, "label": v[1]} for k, v in bootstrap.PIPER_VOICES.items()],
                }
                r.set(WORKER_PREFIX + self.name, json.dumps(info), ex=20)
                if self.current:
                    r.lpush(EVENTS_KEY, json.dumps({"job_id": self.current, "ts": time.time()}))
            except Exception:  # noqa: BLE001 - never let the heartbeat thread die
                log.exception("heartbeat failed")
            time.sleep(5)

    # -- job handlers -------------------------------------------------------

    def _voice(self, job: dict) -> tuple[Path, Path | None]:
        v = job["voice"]
        return data_path(v["model"]), (data_path(v["index"]) if v.get("index") else None)

    def _convert_stage(self, job: dict, src: Path, dst_wav: Path, lo: float, hi: float,
                       pitch_offset: int = 0) -> dict:
        jid, model, index = job["id"], *self._voice(job)
        params = dict(job["params"])
        params["pitch"] = int(params.get("pitch", 0)) + pitch_offset
        self.progress(jid, lo, "Converting voice")
        return self.engine.convert(
            src, dst_wav, model, index, params,
            progress=lambda p: self.progress(jid, lo + (hi - lo) * p),
            check_cancel=lambda: self.check_cancel(jid))

    def _finish(self, job: dict, files: dict[str, Path]) -> dict:
        """Encode working WAVs into the requested format and drop the WAVs."""
        out_dir, fmt = data_path(job["out_dir"]), job["params"].get("format", "mp3")
        self.progress(job["id"], 0.97, "Encoding")
        outputs = {}
        for name, wav in files.items():
            dst = out_dir / f"{name}.{fmt}"
            audio.encode(wav, dst, fmt, title=job.get("title"))
            outputs[name] = f"{job['out_dir']}/{dst.name}"
        return outputs

    def handle_convert(self, job: dict) -> dict:
        work = data_path(job["out_dir"]) / "work"
        work.mkdir(parents=True, exist_ok=True)
        meta = self._convert_stage(job, data_path(job["input"]), work / "output.wav", 0.02, 0.96)
        return {"outputs": self._finish(job, {"output": work / "output.wav"}), "meta": meta}

    def handle_cover(self, job: dict) -> dict:
        from .separate import Separator

        jid, p = job["id"], job["params"]
        work = data_path(job["out_dir"]) / "work"
        work.mkdir(parents=True, exist_ok=True)
        vocals, inst = work / "source_vocals.wav", work / "instrumental.wav"
        key = int(p.get("song_key", 0))

        self.progress(jid, 0.01, "Separating vocals from the music")
        Separator().separate(
            data_path(job["input"]), vocals, inst,
            progress=lambda x: self.progress(jid, 0.01 + 0.44 * x),
            check_cancel=lambda: self.check_cancel(jid))

        # A song-key change moves the vocal and the instrumental together.
        meta = self._convert_stage(job, vocals, work / "vocals.wav", 0.45, 0.9, pitch_offset=key)

        self.progress(jid, 0.92, "Mixing")
        audio.mix(work / "vocals.wav", inst, work / "output.wav",
                  vocal_gain_db=float(p.get("vocal_gain_db", 0)),
                  inst_gain_db=float(p.get("inst_gain_db", 0)),
                  reverb=float(p.get("reverb", 0.15)), inst_semitones=key)
        files = {"output": work / "output.wav", "vocals": work / "vocals.wav", "instrumental": inst}
        return {"outputs": self._finish(job, files), "meta": meta}

    def handle_tts(self, job: dict) -> dict:
        jid, p = job["id"], job["params"]
        work = data_path(job["out_dir"]) / "work"
        work.mkdir(parents=True, exist_ok=True)
        self.progress(jid, 0.02, "Generating speech")
        tts.synthesize(p["text"], p["tts_voice"], work / "narration.wav", float(p.get("speed", 1.0)))
        meta = self._convert_stage(job, work / "narration.wav", work / "output.wav", 0.25, 0.96)
        return {"outputs": self._finish(job, {"output": work / "output.wav"}), "meta": meta}

    def handle_inspect(self, job: dict) -> dict:
        model, index = self._voice(job)
        return {"outputs": {}, "meta": self.engine.inspect(model, index)}

    def handle_train(self, job: dict) -> dict:
        jid = job["id"]
        # Training runs in subprocesses; free this process's models first.
        self.engine._voices.clear()
        self.engine._free()
        try:
            meta = training.train(
                jid, data_path(job["dataset_dir"]), data_path(job["voice_dir"]), job["params"],
                gpu=self.engine.device != "cpu",
                emit=lambda **f: self.emit(jid, **f),
                is_canceled=lambda: self.is_canceled(jid))
        except training.Canceled:
            raise Canceled() from None
        return {"outputs": {}, "meta": meta}

    # -- main loop ----------------------------------------------------------

    def run_job(self, job: dict) -> None:
        jid = job["id"]
        if self.is_canceled(jid):
            self.emit(jid, status="canceled")
            return

        self.current = jid
        self.emit(jid, status="running", progress=0.0, stage="Starting")
        started = time.time()
        try:
            result = getattr(self, f"handle_{job['type']}")(job)
            self.emit(jid, status="succeeded", progress=1.0, stage="Done",
                      seconds=round(time.time() - started, 1), **result)
        except Canceled:
            self.emit(jid, status="canceled")
        except USER_ERRORS as e:
            log.warning("job %s failed: %s", jid, e)
            self.emit(jid, status="failed", error=str(e))
        except MemoryError:
            self.emit(jid, status="failed", error="The worker ran out of memory. Try a shorter file.")
        except Exception as e:  # noqa: BLE001
            log.error("job %s crashed:\n%s", jid, traceback.format_exc())
            self.emit(jid, status="failed", error=f"Unexpected error in the voice engine ({type(e).__name__}).")
        finally:
            self.current = None
            self.redis.delete(CANCEL_PREFIX + jid)
            if job.get("out_dir"):
                shutil.rmtree(data_path(job["out_dir"]) / "work", ignore_errors=True)

    def run(self) -> None:
        threading.Thread(target=self.heartbeat, daemon=True).start()

        while lacking := bootstrap.missing():
            log.warning("waiting for base models: %s", ", ".join(lacking))
            time.sleep(10)

        self.engine = Engine()
        log.info("engine ready on %s; serving queues %s", self.engine.device, WORKER_QUEUES)

        queues = [QUEUE_PREFIX + q for q in WORKER_QUEUES]
        while True:
            try:
                item = self.redis.brpop(queues, timeout=5)
            except redis.RedisError:
                log.exception("redis unavailable; retrying")
                time.sleep(3)
                continue
            if item:
                self.run_job(json.loads(item[1]))
                if MAX_RSS_MB and (rss := rss_mb()) > MAX_RSS_MB:
                    log.warning("resident memory is %d MB (limit %d); restarting clean", rss, MAX_RSS_MB)
                    return


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Worker().run()


if __name__ == "__main__":
    main()
