import { ArrowLeft, Download, FileUp, Flag, Mic, Trash2, Upload, Wand2 } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, isActive, type DatasetFile, type Job, type System, type Voice } from "../api";
import { Recorder } from "../components/Recorder";
import { Chip, ErrorNote, Field, ProgressBar, Range, Spinner } from "../components/ui";
import { VoiceAvatar } from "../components/VoicePicker";
import { clock, minutes, usePolled } from "../hooks";
import { VoiceStatusChip } from "./Voices";

// Short passages with varied sounds and moods, so a set of takes covers more
// of what the voice can do than one long monotone read.
const PROMPTS = [
  "The quick brown fox jumps over the lazy dog, then circles back to check if anyone was watching.",
  "Honestly? I never thought we'd make it this far. But here we are, and the view is worth every step.",
  "Six thick thistle sticks. She sells seashells by the seashore. Unique New York, unique New York.",
  "When the rain finally stopped, the whole street smelled like wet stone and orange blossoms.",
  "Wait, wait, wait. You're telling me the meeting was yesterday? Why didn't anybody say something?",
  "Measure twice, cut once. My grandfather said that about wood, but it works for almost everything.",
  "Zebras, jaguars and oxen mingled quietly by the vast, frozen lake, puzzled by the bright haze.",
  "It's fine. Really. I just need a minute, a glass of water, and maybe a very long holiday.",
  "Three, two, one... and we're live! Good evening everyone, and welcome back to the show.",
  "Softly now, so we don't wake them. Close the door behind you and leave the hall light on.",
];

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="card p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 className="text-lg font-bold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** How close the recordings are to the amount a good voice needs. */
function Readiness({ voice }: { voice: Voice }) {
  const s = voice.dataset_summary!;
  const tone = s.level === "good" ? "text-good" : s.level === "ok" ? "text-warn" : "text-muted";
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="font-display text-3xl font-bold tabular-nums">{minutes(s.voiced_seconds)}</span>
        <span className="hint">of speech · goal {minutes(s.good_seconds)}</span>
      </div>
      <ProgressBar value={s.voiced_seconds / s.good_seconds} tone={s.level === "good" ? "good" : "accent"} />
      <p className={`text-sm mt-2 ${tone}`}>{s.text}</p>
      {s.flagged > 0 && <p className="text-sm text-bad mt-1">{s.flagged} recording{s.flagged > 1 ? "s have" : " has"} clipping. Replace them before training.</p>}
    </div>
  );
}

function RecordingRow({ file, onDelete, locked }: { file: DatasetFile; onDelete: () => void; locked: boolean }) {
  const [open, setOpen] = useState(false);
  const issues = file.analysis.issues ?? [];
  return (
    <li className="py-3">
      <div className="flex items-center gap-3">
        <button type="button" className="min-w-0 flex-1 text-left cursor-pointer" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="block truncate text-sm font-medium">{file.filename}</span>
          <span className="hint">{clock(file.duration)}{open ? "" : " · click to listen"}</span>
        </button>
        {issues.length === 0 ? <Chip tone="good">Clean</Chip> : <Chip tone={issues.some((i) => i.level === "bad") ? "bad" : "warn"}>{issues.length} issue{issues.length > 1 ? "s" : ""}</Chip>}
        <button type="button" className="btn btn-ghost px-2" onClick={onDelete} disabled={locked} aria-label={`Remove ${file.filename}`}>
          <Trash2 className="size-4" />
        </button>
      </div>
      {issues.map((i) => <p key={i.text} className={`text-[13px] mt-1 ${i.level === "bad" ? "text-bad" : "text-warn"}`}>{i.text}</p>)}
      {open && <audio controls preload="metadata" src={file.url} className="mt-2" />}
    </li>
  );
}

export default function VoiceDetail({ system }: { system: System | null }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const busyState = (v: Voice | null) => v?.status === "training" || v?.status === "validating";
  const { data: voice, error: loadError, reload, setData } = usePolled<Voice>(`/voices/${id}`, (v) => (busyState(v) ? 2500 : 20000));
  const { data: jobs, reload: reloadJobs } = usePolled<Job[]>("/jobs", () => (busyState(voice) ? 2500 : 20000));

  const [path, setPath] = useState<"build" | "import" | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState<number | null>(null);
  const [rejected, setRejected] = useState<{ filename: string; reason: string }[]>([]);
  const [promptIndex, setPromptIndex] = useState(0);
  const [epochs, setEpochs] = useState<number | null>(null);
  const [batch, setBatch] = useState(4);
  const [shareOk, setShareOk] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [reportText, setReportText] = useState("");
  const [reported, setReported] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const pth = useRef<HTMLInputElement>(null);
  const idx = useRef<HTMLInputElement>(null);

  if (loadError && !voice) {
    return <div className="space-y-4"><ErrorNote>{loadError}</ErrorNote><Link to="/voices" className="btn btn-secondary">Back to voices</Link></div>;
  }
  if (!voice) return <Spinner className="size-5 text-muted" />;

  const trainJob = jobs?.find((j) => j.type === "train" && j.voice_id === voice.id);
  const locked = busyState(voice);
  const gpu = system?.device === "gpu";
  const chosenEpochs = epochs ?? (gpu ? 200 : 20);
  const tab = path ?? (voice.source === "upload" ? "import" : "build");

  async function run(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await Promise.all([reload(), reloadJobs()]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(null);
    }
  }

  const addRecordings = (files: File[]) => run(async () => {
    if (!files.length) return;
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    setUploading(0);
    const res = await api.upload<{ rejected: typeof rejected }>(`/voices/${voice.id}/dataset`, form, setUploading);
    setRejected(res.rejected);
  });

  const importModel = () => run(async () => {
    const model = pth.current?.files?.[0];
    if (!model) throw new Error("Choose the voice's .zip or .pth file first.");
    const form = new FormData();
    form.set("model", model);
    const index = idx.current?.files?.[0];
    if (index && !model.name.toLowerCase().endsWith(".zip")) form.set("index", index);
    setUploading(0);
    setData(await api.upload<Voice>(`/voices/${voice.id}/model`, form, setUploading));
  });

  const consentLine = voice.consent
    ? `My name is ${voice.consent.name}. I give permission for my voice to be cloned and used on Voicely.`
    : "";

  return (
    <div className="space-y-6">
      <Link to="/voices" className="btn btn-ghost px-2 -ml-2"><ArrowLeft className="size-4" /> All voices</Link>

      <header className="flex flex-wrap items-center gap-4">
        <VoiceAvatar voice={voice} size="size-16 text-2xl" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold truncate">{voice.name}</h1>
            <VoiceStatusChip voice={voice} />
          </div>
          <p className="text-muted mt-1">
            {voice.description || (voice.is_owner ? "Your voice model." : `Shared by ${voice.owner_name}.`)}
            {voice.status === "ready" && voice.meta.sample_rate && (
              <span className="font-mono text-[12px] ml-2">
                {voice.meta.sample_rate / 1000} kHz · RVC {voice.meta.version}{voice.has_index ? " · indexed" : ""}{voice.meta.epochs ? ` · ${voice.meta.epochs} epochs` : ""}
              </span>
            )}
          </p>
        </div>
        {voice.status === "ready" && (
          <div className="flex flex-wrap gap-2">
            {voice.is_owner && (
              <button type="button" className="btn btn-secondary" disabled={downloading}
                title={voice.has_index ? "A zip with the .pth model and its .index" : "A zip with the .pth model"}
                onClick={async () => {
                  setDownloading(true);
                  await run(() => api.download(`/voices/${voice.id}/model.zip`, `${voice.name.trim().replace(/\s+/g, "_")}-voicely.zip`));
                  setDownloading(false);
                }}>
                {downloading ? <Spinner /> : <Download className="size-4" />} {downloading ? "Preparing…" : "Download model"}
              </button>
            )}
            <button type="button" className="btn btn-primary" onClick={() => navigate(`/?voice=${voice.id}`)}>
              <Wand2 className="size-4" /> Use this voice
            </button>
          </div>
        )}
      </header>

      <ErrorNote>{error}</ErrorNote>
      {voice.is_owner && voice.status === "failed" && <ErrorNote>{voice.status_detail || "The last attempt to build this voice failed."}</ErrorNote>}
      {voice.is_owner && voice.status === "ready" && voice.status_detail && <p className="text-sm text-warn">{voice.status_detail}</p>}

      {voice.status === "validating" && (
        <div className="card p-5 flex items-center gap-3"><Spinner className="text-accent" /> Checking that the uploaded model loads safely…</div>
      )}

      {voice.status === "training" && (
        <Section title="Training in progress" aside={trainJob && isActive(trainJob) && (
          <button type="button" className="btn btn-ghost text-[13px]" onClick={() => run(() => api.post(`/jobs/${trainJob.id}/cancel`))}>Stop training</button>
        )}>
          <ProgressBar value={trainJob?.progress ?? 0} />
          <div className="flex justify-between mt-2">
            <span className="hint">{trainJob?.status === "queued" ? "Waiting for the engine" : trainJob?.stage || "Starting"}</span>
            <span className="font-mono text-[13px] text-muted tabular-nums">{Math.round((trainJob?.progress ?? 0) * 100)}%</span>
          </div>
          <p className="hint mt-3">You can close this page. Training keeps running, and the voice becomes usable when it finishes.</p>
          {trainJob?.log && (
            <details className="text-sm mt-3">
              <summary className="cursor-pointer text-muted hover:text-text">Training log</summary>
              <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-ink border border-line p-3 font-mono text-[12px] text-muted whitespace-pre-wrap">{trainJob.log}</pre>
            </details>
          )}
        </Section>
      )}

      {voice.is_owner ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2" role="tablist">
            {([["build", Mic, "Build it from recordings", "Record or upload 10+ minutes of the voice and train a model here."],
               ["import", FileUp, "Import a trained model", "Trained on Colab? Bring the .zip here. A .pth from Applio or RVC WebUI works too."]] as const).map(([key, Icon, title, sub]) => (
              <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setPath(key)}
                className={`card p-4 text-left cursor-pointer transition-colors ${tab === key ? "border-accent bg-accent/10" : "hover:border-muted"}`}>
                <Icon className={`size-5 ${tab === key ? "text-accent" : "text-muted"}`} aria-hidden />
                <p className="font-display font-bold text-lg mt-2">{title}</p>
                <p className="hint">{sub}</p>
              </button>
            ))}
          </div>

          {tab === "build" && voice.dataset_summary && (
            <>
              <Section title="1. Recordings" aside={<Link to="/guide" className="text-sm text-accent hover:underline">What makes a good recording?</Link>}>
                <div className="grid gap-6 lg:grid-cols-2">
                  <div className="space-y-5">
                    <Readiness voice={voice} />
                    <div
                      role="button" tabIndex={0}
                      onClick={() => !locked && picker.current?.click()}
                      onKeyDown={(e) => e.key === "Enter" && !locked && picker.current?.click()}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => { e.preventDefault(); if (!locked) addRecordings([...e.dataTransfer.files]); }}
                      className={`rounded-xl border-2 border-dashed border-line px-5 py-7 text-center transition-colors ${locked ? "opacity-50" : "cursor-pointer hover:border-muted"}`}
                    >
                      <Upload className="size-5 mx-auto text-muted" aria-hidden />
                      <p className="font-medium mt-2">Add recordings</p>
                      <p className="hint">Drop audio files or click to browse. Several at once is fine.</p>
                      <input ref={picker} type="file" accept="audio/*,.wav,.mp3,.flac,.m4a,.ogg,.webm" multiple hidden
                        onChange={(e) => { addRecordings([...(e.target.files ?? [])]); e.target.value = ""; }} />
                    </div>
                    {uploading !== null && <div className="space-y-1.5"><ProgressBar value={uploading} /><p className="hint">{uploading < 1 ? "Uploading…" : "Measuring quality…"}</p></div>}
                    {rejected.map((r) => <p key={r.filename} className="text-sm text-bad">{r.filename}: {r.reason}</p>)}

                    <div className="rounded-xl bg-ink border border-line p-4 space-y-3">
                      <p className="eyebrow">Or record here · passage {promptIndex + 1} of {PROMPTS.length}</p>
                      <p className="font-display text-lg leading-snug">“{PROMPTS[promptIndex]}”</p>
                      <div className="flex flex-wrap items-center gap-3">
                        {locked ? <span className="hint">Recording is paused while the voice is processing.</span> : (
                          <Recorder actionLabel="Add to recordings" onRecorded={async (f) => { await addRecordings([f]); setPromptIndex((promptIndex + 1) % PROMPTS.length); }} />
                        )}
                        <button type="button" className="btn btn-ghost text-[13px]" onClick={() => setPromptIndex((promptIndex + 1) % PROMPTS.length)}>Different passage</button>
                      </div>
                      <p className="hint">Read naturally, the way you'd actually speak or sing. These passages are short: for a full voice, also upload longer recordings.</p>
                    </div>
                  </div>

                  <div>
                    {voice.dataset!.length === 0 ? (
                      <p className="hint">No recordings yet. Each one is checked for clipping, noise and silence as it arrives.</p>
                    ) : (
                      <ul className="divide-y divide-line max-h-[34rem] overflow-auto pr-1">
                        {voice.dataset!.map((f) => <RecordingRow key={f.id} file={f} locked={locked} onDelete={() => run(() => api.del(`/voices/${voice.id}/dataset/${f.id}`))} />)}
                      </ul>
                    )}
                  </div>
                </div>
              </Section>

              <Section title="2. Train">
                <div className="grid gap-6 lg:grid-cols-2">
                  <div className="space-y-5">
                    <Range label="Training passes (epochs)" value={chosenEpochs} min={gpu ? 50 : 2} max={gpu ? 600 : 100} step={gpu ? 25 : 2} onChange={setEpochs}
                      hint="More passes fit the voice more closely. 200 to 300 suits 10 to 30 minutes of audio; far more can overfit." />
                    <Range label="Batch size" value={batch} min={1} max={gpu ? 16 : 8} step={1} onChange={setBatch}
                      hint="Clips per step. Lower it if training runs out of memory." />
                    <button type="button" className="btn btn-primary" disabled={locked || voice.dataset_summary.level === "low" || !system?.can_train}
                      onClick={() => run(() => api.post(`/voices/${voice.id}/train`, { epochs: chosenEpochs, batch_size: batch }))}>
                      <Wand2 className="size-4" /> {voice.source === "trained" ? "Retrain this voice" : "Start training"}
                    </button>
                    {voice.dataset_summary.level === "low" && <p className="hint">Add at least {minutes(voice.dataset_summary.min_seconds)} of speech to enable training.</p>}
                    {system && !system.can_train && <p className="hint">The engine isn't ready to train yet. Check the status in the top bar.</p>}
                  </div>
                  <div className="rounded-xl border border-line bg-ink p-4 space-y-3 text-sm">
                    <p className="eyebrow">{gpu ? "Alternative" : "Recommended for this server"}</p>
                    <h3 className="font-bold text-base">Train on a free Google Colab GPU</h3>
                    <p className="text-muted">
                      {gpu
                        ? `This server has a GPU (${system?.gpu}), so training here is the simplest route. Colab works too.`
                        : "This server has no NVIDIA GPU, so training here takes hours even for a rough voice. Colab runs 200 epochs on the same recordings far faster, for free."}
                    </p>
                    <ol className="space-y-3 list-none">
                      <li className="flex gap-3">
                        <span className="font-mono text-accent">1</span>
                        <div className="space-y-2">
                          <p>Download your recordings and the training notebook.</p>
                          <div className="flex flex-wrap gap-2">
                            <button type="button" className="btn btn-secondary" disabled={!voice.dataset!.length}
                              onClick={() => run(() => api.download(`/voices/${voice.id}/dataset.zip`, `${voice.name}-dataset.zip`))}>
                              <Download className="size-4" /> Recordings (.zip)
                            </button>
                            <a className="btn btn-secondary" href="/voicely-train-colab.ipynb" download>
                              <Download className="size-4" /> Notebook (.ipynb)
                            </a>
                          </div>
                        </div>
                      </li>
                      <li className="flex gap-3">
                        <span className="font-mono text-accent">2</span>
                        <p>
                          Open <a className="text-accent hover:underline" href="https://colab.research.google.com/" target="_blank" rel="noreferrer">colab.research.google.com</a>,
                          choose <strong>File → Upload notebook</strong> and pick the notebook.
                        </p>
                      </li>
                      <li className="flex gap-3">
                        <span className="font-mono text-accent">3</span>
                        <p>In Colab: <strong>Runtime → Change runtime type → T4 GPU</strong>, then <strong>Runtime → Run all</strong>. Upload the recordings zip when it asks.</p>
                      </li>
                      <li className="flex gap-3">
                        <span className="font-mono text-accent">4</span>
                        <div className="space-y-2">
                          <p>When it finishes, Colab downloads one file ending in <span className="font-mono text-[12px]">-voicely.zip</span>. Import it here.</p>
                          <button type="button" className="btn btn-secondary" onClick={() => setPath("import")}><FileUp className="size-4" /> Import the result</button>
                        </div>
                      </li>
                    </ol>
                    <p className="hint">More detail and troubleshooting in the <Link to="/guide#colab" className="text-accent hover:underline">guide</Link>.</p>
                  </div>
                </div>
              </Section>
            </>
          )}

          {tab === "import" && (
            <Section title="Import a trained model">
              <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-4">
                  <Field label="Voice model (.zip or .pth)" hint="The -voicely.zip from the Colab notebook, or the small .pth (about 55 MB) from a 'weights' folder. Not G_*.pth or D_*.pth.">
                    <input ref={pth} type="file" accept=".pth,.zip" className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-text" />
                  </Field>
                  <Field label="Index (.index, optional)" hint="Only needed with a bare .pth: the file starting with 'added_'. A zip already includes it.">
                    <input ref={idx} type="file" accept=".index" className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-text" />
                  </Field>
                  {uploading !== null && <div className="space-y-1.5"><ProgressBar value={uploading} /><p className="hint">{uploading < 1 ? `Uploading… ${Math.round(uploading * 100)}%` : "Saving…"}</p></div>}
                  <button type="button" className="btn btn-primary" disabled={locked || uploading !== null} onClick={importModel}>
                    <FileUp className="size-4" /> {voice.status === "ready" ? "Replace model" : "Import model"}
                  </button>
                </div>
                <div className="text-sm space-y-2 text-muted">
                  <p>Works with RVC v1 and v2 models from any trainer that follows the standard format.</p>
                  <p>The file is opened in a restricted mode that only accepts model weights, then checked against its index. Anything else is rejected.</p>
                  <p>Only import a model of your own voice or one you have permission for. Models of celebrities or other real people shared online are not yours to use.</p>
                </div>
              </div>
            </Section>
          )}

          <Section title="Permission on record">
            <div className="grid gap-6 lg:grid-cols-2">
              <dl className="text-sm space-y-2">
                <div className="flex justify-between gap-4"><dt className="text-muted">Voice of</dt><dd>{voice.consent!.name}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-muted">Basis</dt><dd>{voice.consent!.type === "self" ? "Own voice" : "With their permission"}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-muted">Confirmed</dt><dd>{new Date(voice.consent!.at).toLocaleDateString(undefined, { dateStyle: "medium" })}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-muted">Spoken statement</dt><dd>{voice.consent!.has_audio ? <Chip tone="good">On file</Chip> : "Not recorded"}</dd></div>
              </dl>
              <div className="space-y-3">
                <p className="text-sm">
                  {voice.consent!.has_audio ? "A spoken statement is saved. Record again to replace it." : "Strengthen the record: have the voice's owner read this aloud."}
                </p>
                <p className="font-display text-lg leading-snug">“{consentLine}”</p>
                <Recorder maxSeconds={30} actionLabel="Save statement" onRecorded={(f) => run(async () => {
                  const form = new FormData();
                  form.set("file", f);
                  setData(await api.upload<Voice>(`/voices/${voice.id}/consent-audio`, form));
                })} />
              </div>
            </div>
          </Section>

          <Section title="Sharing">
            {voice.visibility === "public" ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm">Everyone with an account on this server can use this voice.</p>
                <button type="button" className="btn btn-secondary" onClick={() => run(() => api.patch(`/voices/${voice.id}`, { visibility: "private" }))}>Make private</button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm">Private. Only you can use this voice.</p>
                <label className="flex gap-3 items-start cursor-pointer text-sm">
                  <input type="checkbox" className="mt-1 size-4 accent-accent" checked={shareOk} onChange={(e) => setShareOk(e.target.checked)} />
                  <span>{voice.consent!.name} agreed that other people on this server may make audio with this voice.</span>
                </label>
                <button type="button" className="btn btn-secondary" disabled={!shareOk || voice.status !== "ready"}
                  onClick={() => run(() => api.patch(`/voices/${voice.id}`, { visibility: "public", sharing_confirmed: true }))}>
                  Share with everyone here
                </button>
                {voice.status !== "ready" && <p className="hint">A voice can be shared once it's ready.</p>}
              </div>
            )}
          </Section>

          <div className="flex justify-end gap-2">
            {confirmDelete ? (
              <>
                <span className="hint self-center">Delete the model, recordings and consent record for good?</span>
                <button type="button" className="btn btn-danger" onClick={() => run(async () => { await api.del(`/voices/${voice.id}`); navigate("/voices"); })}>Delete voice</button>
                <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>Keep</button>
              </>
            ) : (
              <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(true)}><Trash2 className="size-4" /> Delete voice</button>
            )}
          </div>
        </>
      ) : (
        <Section title="Report this voice">
          {reported ? <p className="text-sm text-good">Thanks. The report was recorded for the server's administrator.</p> : (
            <div className="space-y-3 max-w-xl">
              <p className="text-sm text-muted">If this voice imitates someone who didn't agree to it, tell the administrator.</p>
              <textarea className="input min-h-24" value={reportText} onChange={(e) => setReportText(e.target.value)} placeholder="What's wrong with this voice?" maxLength={1000} />
              <button type="button" className="btn btn-secondary" disabled={reportText.trim().length < 5}
                onClick={() => run(async () => { await api.post(`/voices/${voice.id}/report`, { reason: reportText }); setReported(true); })}>
                <Flag className="size-4" /> Send report
              </button>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
