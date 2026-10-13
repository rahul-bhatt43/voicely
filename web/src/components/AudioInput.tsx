import { FileAudio, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Recorder } from "./Recorder";

const ACCEPT = "audio/*,.wav,.mp3,.flac,.m4a,.aac,.ogg,.opus,.webm,.mp4";

/** Pick one audio file by drop, browse or (optionally) recording. */
export function AudioInput({ file, onChange, allowRecording = false, prompt, maxMb }: {
  file: File | null;
  onChange: (file: File | null) => void;
  allowRecording?: boolean;
  prompt: string;
  maxMb: number;
}) {
  const [over, setOver] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [tooBig, setTooBig] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) return setUrl(null);
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  function pick(f: File | undefined) {
    if (!f) return;
    const big = f.size > maxMb * 1024 * 1024;
    setTooBig(big);
    if (!big) onChange(f);
  }

  if (file && url) {
    return (
      <div className="rounded-xl border border-line bg-ink p-4 space-y-3">
        <div className="flex items-center gap-3">
          <FileAudio className="size-5 text-accent shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{file.name}</p>
            <p className="hint">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
          </div>
          <button type="button" className="btn btn-ghost px-2" onClick={() => onChange(null)} aria-label="Remove file">
            <X className="size-4" />
          </button>
        </div>
        <audio controls src={url} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); }}
        className={`rounded-xl border-2 border-dashed px-6 py-10 text-center cursor-pointer transition-colors ${over ? "border-accent bg-accent/5" : "border-line hover:border-muted"}`}
      >
        <Upload className="size-6 mx-auto text-muted" aria-hidden />
        <p className="mt-3 font-medium">{prompt}</p>
        <p className="hint mt-1">Drop a file here or click to browse. MP3, WAV, FLAC, M4A, up to {maxMb} MB.</p>
        <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      {tooBig && <p className="text-sm text-bad">That file is over the {maxMb} MB limit.</p>}
      {allowRecording && (
        <div className="flex items-center gap-3">
          <span className="hint">or</span>
          <Recorder onRecorded={(f) => onChange(f)} actionLabel="Use this recording" />
        </div>
      )}
    </div>
  );
}
