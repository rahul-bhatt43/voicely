import { Mic, RotateCcw, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { clock } from "../hooks";
import { ErrorNote } from "./ui";

/**
 * Records from the microphone and hands back a File. The live meter is there
 * to coach levels: recordings that clip or sit near silence make poor
 * training data and poor conversion sources.
 */
export function Recorder({ onRecorded, actionLabel = "Use this take", maxSeconds = 300 }: {
  onRecorded: (file: File) => void | Promise<void>;
  actionLabel?: string;
  maxSeconds?: number;
}) {
  const [state, setState] = useState<"idle" | "recording" | "review">("idle");
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [clipped, setClipped] = useState(false);
  const [take, setTake] = useState<{ file: File; url: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const session = useRef<{ stop: () => void } | null>(null);

  useEffect(() => () => session.current?.stop(), []);
  useEffect(() => () => { if (take) URL.revokeObjectURL(take.url); }, [take]);

  async function start() {
    setError("");
    let stream: MediaStream;
    try {
      // Browser "enhancements" pump and gate the signal, which hurts a voice model.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
    } catch {
      setError("Microphone access was blocked. Allow it in your browser's site settings, then try again.");
      return;
    }

    const recorder = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const startedAt = Date.now();
    let raf = 0;

    const meter = () => {
      analyser.getFloatTimeDomainData(buf);
      const peak = buf.reduce((m, v) => Math.max(m, Math.abs(v)), 0);
      setLevel(peak);
      if (peak > 0.98) setClipped(true);
      const elapsed = (Date.now() - startedAt) / 1000;
      setSeconds(elapsed);
      if (elapsed >= maxSeconds) return recorder.stop();
      raf = requestAnimationFrame(meter);
    };

    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
      session.current = null;
      const type = recorder.mimeType || "audio/webm";
      const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
      const file = new File(chunks, `recording-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.${ext}`, { type });
      setTake({ file, url: URL.createObjectURL(file) });
      setState("review");
    };

    session.current = { stop: () => recorder.state !== "inactive" && recorder.stop() };
    setClipped(false);
    setSeconds(0);
    recorder.start();
    setState("recording");
    meter();
  }

  function discard() {
    setTake(null);
    setState("idle");
  }

  async function accept() {
    if (!take) return;
    setBusy(true);
    try {
      await onRecorded(take.file);
      discard();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {state === "idle" && (
        <button type="button" className="btn btn-secondary" onClick={start}>
          <Mic className="size-4" /> Start recording
        </button>
      )}

      {state === "recording" && (
        <div className="flex items-center gap-4">
          <button type="button" className="btn btn-primary" onClick={() => session.current?.stop()}>
            <Square className="size-4 fill-current" /> Stop
          </button>
          <span className="font-mono tabular-nums text-sm">{clock(seconds)}</span>
          <div className="flex-1 h-2 rounded-full bg-line overflow-hidden" aria-label="Input level">
            <div
              className={`h-full rounded-full ${level > 0.9 ? "bg-bad" : level > 0.05 ? "bg-good" : "bg-muted"}`}
              style={{ width: `${Math.min(100, Math.sqrt(level) * 100)}%` }}
            />
          </div>
        </div>
      )}

      {state === "review" && take && (
        <div className="space-y-3">
          <audio controls src={take.url} />
          {clipped && (
            <p className="text-sm text-warn">This take hit the top of the meter. Move back from the mic and record it again for a cleaner result.</p>
          )}
          <div className="flex gap-2">
            <button type="button" className="btn btn-primary" onClick={accept} disabled={busy}>{busy ? "Saving…" : actionLabel}</button>
            <button type="button" className="btn btn-ghost" onClick={discard} disabled={busy}>
              <RotateCcw className="size-4" /> Record again
            </button>
          </div>
        </div>
      )}

      <ErrorNote>{error}</ErrorNote>
    </div>
  );
}
