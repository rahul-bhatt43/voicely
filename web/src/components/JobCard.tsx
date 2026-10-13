import { ChevronDown, Download, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, isActive, type Job } from "../api";
import { ago, clock } from "../hooks";
import { Chip, Equalizer, ErrorNote, ProgressBar } from "./ui";

export const JOB_LABEL: Record<Job["type"], string> = {
  cover: "Song cover",
  convert: "Voice swap",
  tts: "Text to voice",
  train: "Training",
};

function StatusChip({ job }: { job: Job }) {
  switch (job.status) {
    case "queued": return <Chip>Waiting in line</Chip>;
    case "running": return <Chip tone="accent"><Equalizer className="h-3" /> Working</Chip>;
    case "succeeded": return <Chip tone="good">Done</Chip>;
    case "failed": return <Chip tone="bad">Failed</Chip>;
    case "canceled": return <Chip>Canceled</Chip>;
  }
}

function Track({ label, file }: { label: string; file: { url: string; download_url: string } }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium">{label}</span>
        <a href={file.download_url} className="btn btn-ghost px-2 py-1 text-[13px]">
          <Download className="size-3.5" /> Download
        </a>
      </div>
      <audio controls preload="metadata" src={file.url} />
    </div>
  );
}

export function JobCard({ job, onChanged }: { job: Job; onChanged: () => void }) {
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const active = isActive(job);
  const { output, vocals, instrumental } = job.outputs;

  async function act(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <article className="card p-5 space-y-4 min-w-0">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-bold text-lg truncate">{job.title || JOB_LABEL[job.type]}</h3>
          <p className="hint mt-0.5">
            {JOB_LABEL[job.type]}
            {job.voice_name && <> · {job.voice_id ? <Link className="hover:text-text underline-offset-2 hover:underline" to={`/voices/${job.voice_id}`}>{job.voice_name}</Link> : job.voice_name}</>}
            {" · "}{ago(job.created_at)}
            {job.status === "succeeded" && job.seconds != null && <> · took {clock(job.seconds)}</>}
          </p>
        </div>
        <StatusChip job={job} />
      </div>

      {active && (
        <div className="space-y-2">
          <ProgressBar value={job.progress} />
          <div className="flex items-center justify-between">
            <span className="hint">{job.status === "queued" ? "Waiting for the engine to pick this up" : job.stage || "Starting"}</span>
            <span className="font-mono text-[13px] text-muted tabular-nums">{Math.round(job.progress * 100)}%</span>
          </div>
        </div>
      )}

      {job.status === "failed" && <ErrorNote>{job.error || "This job failed."}</ErrorNote>}

      {output && <Track label={job.type === "cover" ? "Finished cover" : "Result"} file={output} />}

      {(vocals || instrumental || job.input_url) && job.status === "succeeded" && (
        <div>
          <button type="button" className="btn btn-ghost px-2 py-1 text-[13px]" onClick={() => setMore(!more)} aria-expanded={more}>
            <ChevronDown className={`size-3.5 transition-transform ${more ? "rotate-180" : ""}`} />
            {job.type === "cover" ? "Stems and original" : "Compare with the original"}
          </button>
          {more && (
            <div className="mt-3 space-y-4 border-l-2 border-line pl-4">
              {vocals && <Track label="Converted vocals only" file={vocals} />}
              {instrumental && <Track label="Instrumental only" file={instrumental} />}
              {job.input_url && (
                <div>
                  <span className="text-sm font-medium block mb-1.5">Original upload</span>
                  <audio controls preload="metadata" src={job.input_url} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {job.type === "train" && job.log && (active || job.status === "failed") && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted hover:text-text">Training log</summary>
          <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-ink border border-line p-3 font-mono text-[12px] text-muted whitespace-pre-wrap">{job.log}</pre>
        </details>
      )}

      <ErrorNote>{error}</ErrorNote>

      <div className="flex justify-end gap-2">
        {active ? (
          <button type="button" className="btn btn-ghost text-[13px]" onClick={() => act(() => api.post(`/jobs/${job.id}/cancel`))}>
            <X className="size-3.5" /> Cancel
          </button>
        ) : confirming ? (
          <>
            <span className="hint self-center">Delete this and its audio?</span>
            <button type="button" className="btn btn-danger text-[13px]" onClick={() => act(() => api.del(`/jobs/${job.id}`))}>Delete</button>
            <button type="button" className="btn btn-ghost text-[13px]" onClick={() => setConfirming(false)}>Keep</button>
          </>
        ) : (
          <button type="button" className="btn btn-ghost text-[13px]" onClick={() => setConfirming(true)}>
            <Trash2 className="size-3.5" /> Delete
          </button>
        )}
      </div>
    </article>
  );
}
