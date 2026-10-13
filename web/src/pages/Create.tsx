import { ChevronDown, Mic2, Music, Type } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, type Job, type System, type Voice } from "../api";
import { AudioInput } from "../components/AudioInput";
import { ErrorNote, Field, PageHeader, ProgressBar, Range } from "../components/ui";
import { VoicePicker } from "../components/VoicePicker";
import { usePolled } from "../hooks";

type Mode = "cover" | "convert" | "tts";

const MODES: { id: Mode; icon: typeof Music; title: string; blurb: string }[] = [
  { id: "cover", icon: Music, title: "Song cover", blurb: "A full song with music. We lift the vocals out, re-sing them, and mix them back in." },
  { id: "convert", icon: Mic2, title: "Voice swap", blurb: "Clean speech or a cappella singing, with no music behind it." },
  { id: "tts", icon: Type, title: "Text to voice", blurb: "Type the words. A narrator reads them, then the voice is swapped." },
];

const PITCH_PRESETS = [
  { label: "Deeper source → higher voice", value: 12 },
  { label: "Same range", value: 0 },
  { label: "Higher source → deeper voice", value: -12 },
];

const semitones = (v: number) => (v === 0 ? "no shift" : `${v > 0 ? "+" : ""}${v} semitones`);
const db = (v: number) => `${v > 0 ? "+" : ""}${v} dB`;
const pct = (v: number) => `${Math.round(v * 100)}%`;

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="card p-5 sm:p-6">
      <h2 className="flex items-center gap-3 text-lg font-bold mb-4">
        <span className="size-6 rounded-full bg-raised border border-line grid place-items-center font-mono text-[12px] text-muted">{n}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function Create({ system }: { system: System | null }) {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const { data: voices } = usePolled<Voice[]>("/voices", () => 30000);

  const [mode, setMode] = useState<Mode>("cover");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [narrator, setNarrator] = useState("");
  const [speed, setSpeed] = useState(1);
  const [voiceId, setVoiceId] = useState<string | null>(search.get("voice"));
  const [title, setTitle] = useState("");
  const [advanced, setAdvanced] = useState(false);

  // Engine settings; defaults are the values tested in RVC_ARCHITECTURE.md.
  const [p, setP] = useState({
    pitch: 0, index_rate: 0.66, protect: 0.33, rms_mix_rate: 0.21, filter_radius: 3,
    f0_method: "rmvpe", format: "mp3",
    song_key: 0, vocal_gain_db: 0, inst_gain_db: 0, reverb: 0.15,
  });
  const tune = <K extends keyof typeof p>(k: K) => (v: (typeof p)[K]) => setP((prev) => ({ ...prev, [k]: v }));

  const [busy, setBusy] = useState(false);
  const [uploaded, setUploaded] = useState(0);
  const [error, setError] = useState("");

  const narrators = system?.tts_voices ?? [];
  useEffect(() => {
    if (!narrator && narrators.length) setNarrator(narrators[0].id);
  }, [narrator, narrators]);

  // Preselect the only sensible choice instead of making the user click it.
  useEffect(() => {
    const ready = voices?.filter((v) => v.status === "ready") ?? [];
    if (!voiceId && ready.length === 1) setVoiceId(ready[0].id);
  }, [voices, voiceId]);

  const limits = system?.limits;
  const voice = voices?.find((v) => v.id === voiceId);
  const hasSource = mode === "tts" ? text.trim().length > 0 : file !== null;
  const missing = !hasSource ? (mode === "tts" ? "Type some text" : "Add your audio") : !voice ? "Choose a voice" : null;

  async function submit() {
    if (missing || !voice) return;
    setError("");
    setBusy(true);
    setUploaded(0);
    const { song_key, vocal_gain_db, inst_gain_db, reverb, ...base } = p;
    try {
      let job: Job;
      if (mode === "tts") {
        job = await api.post<Job>("/jobs/tts", { ...base, voice_id: voice.id, text, tts_voice: narrator, speed, title });
      } else {
        const form = new FormData();
        form.set("file", file!);
        form.set("voice_id", voice.id);
        form.set("title", title);
        form.set("params", JSON.stringify(mode === "cover" ? p : base));
        job = await api.upload<Job>(`/jobs/${mode}`, form, setUploaded);
      }
      navigate("/library", { state: { highlight: job.id } });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Create" title="What should your voice perform?">
        The performance supplies the words, timing and melody. The voice you pick supplies the sound.
      </PageHeader>

      <div className="grid gap-3 sm:grid-cols-3 mb-8" role="tablist">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            onClick={() => { setMode(m.id); setError(""); }}
            className={`card p-4 text-left cursor-pointer transition-colors ${mode === m.id ? "border-accent bg-accent/10" : "hover:border-muted"}`}
          >
            <m.icon className={`size-5 ${mode === m.id ? "text-accent" : "text-muted"}`} aria-hidden />
            <p className="font-display font-bold text-lg mt-2">{m.title}</p>
            <p className="hint mt-0.5">{m.blurb}</p>
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem] items-start">
        <div className="space-y-6">
          <Step n={1} title={mode === "tts" ? "The words" : mode === "cover" ? "The song" : "The recording"}>
            {mode === "tts" ? (
              <div className="space-y-4">
                <div>
                  <textarea
                    className="input min-h-36 resize-y"
                    placeholder="Type or paste what you want to hear in the chosen voice…"
                    value={text}
                    maxLength={limits?.max_tts_chars}
                    onChange={(e) => setText(e.target.value)}
                  />
                  <p className="hint mt-1 text-right tabular-nums">{text.length} / {limits?.max_tts_chars ?? "…"}</p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Narrator" hint="Sets the language, accent and pacing. Pick one near the target voice's pitch.">
                    <select className="input" value={narrator} onChange={(e) => setNarrator(e.target.value)}>
                      {narrators.length === 0 && <option value="">Waiting for the engine…</option>}
                      {narrators.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
                    </select>
                  </Field>
                  <Range label="Reading speed" value={speed} min={0.6} max={1.6} step={0.05} format={(v) => `${v.toFixed(2)}×`} onChange={setSpeed} />
                </div>
              </div>
            ) : (
              <>
                <AudioInput
                  file={file}
                  onChange={setFile}
                  allowRecording={mode === "convert"}
                  maxMb={limits?.max_upload_mb ?? 200}
                  prompt={mode === "cover" ? "Add a song" : "Add a voice recording"}
                />
                <p className="hint mt-3">
                  {mode === "cover"
                    ? `Up to ${limits?.max_audio_minutes ?? 10} minutes. Use a song you have the right to use; studio recordings separate more cleanly than live ones.`
                    : "Background music, echo and noise all carry into the result. For a song with music, use Song cover instead."}
                </p>
              </>
            )}
          </Step>

          <Step n={2} title="The voice">
            {voices ? <VoicePicker voices={voices} value={voiceId} onChange={setVoiceId} /> : <p className="hint">Loading voices…</p>}
          </Step>

          <Step n={3} title="Tuning">
            <div className="space-y-6">
              <div>
                <Range label="Pitch" value={p.pitch} min={-12} max={12} step={1} format={semitones} onChange={tune("pitch")}
                  hint="Moves the performance into the target voice's natural range. A full octave (12) keeps a song in key." />
                <div className="flex flex-wrap gap-2 mt-3">
                  {PITCH_PRESETS.map((preset) => (
                    <button key={preset.value} type="button" onClick={() => tune("pitch")(preset.value)}
                      className={`btn px-3 py-1 text-[13px] border ${p.pitch === preset.value ? "border-accent text-accent bg-accent/10" : "border-line text-muted hover:text-text"}`}>
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              {mode === "cover" && (
                <div className="grid gap-6 sm:grid-cols-2">
                  <Range label="Vocal volume" value={p.vocal_gain_db} min={-12} max={12} step={1} format={db} onChange={tune("vocal_gain_db")} />
                  <Range label="Music volume" value={p.inst_gain_db} min={-12} max={12} step={1} format={db} onChange={tune("inst_gain_db")} />
                  <Range label="Reverb on the vocal" value={p.reverb} min={0} max={1} step={0.05} format={pct} onChange={tune("reverb")}
                    hint="A little room sound helps the new vocal sit in the mix." />
                  <Range label="Song key" value={p.song_key} min={-6} max={6} step={1} format={semitones} onChange={tune("song_key")}
                    hint="Transposes vocal and music together, for when an octave is too far." />
                </div>
              )}

              <div>
                <button type="button" className="btn btn-ghost px-2 -ml-2" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}>
                  <ChevronDown className={`size-4 transition-transform ${advanced ? "rotate-180" : ""}`} /> Advanced
                </button>
                {advanced && (
                  <div className="grid gap-6 sm:grid-cols-2 mt-4">
                    <Range label="Voice character" value={p.index_rate} min={0} max={1} step={0.01} format={pct} onChange={tune("index_rate")}
                      hint={voice && !voice.has_index ? "This voice has no index file, so this setting has no effect." : "How hard to pull the sound toward the target speaker. Lower it if you hear artifacts."} />
                    <Range label="Consonant protection" value={p.protect} min={0} max={0.5} step={0.01} format={(v) => v.toFixed(2)} onChange={tune("protect")}
                      hint="Lower values protect breaths and consonants more. 0.50 turns protection off." />
                    <Range label="Loudness source" value={p.rms_mix_rate} min={0} max={1} step={0.01} format={pct} onChange={tune("rms_mix_rate")}
                      hint="0% follows the original performance's loudness; 100% keeps the converted voice's own." />
                    <Range label="Pitch smoothing" value={p.filter_radius} min={0} max={7} step={1} onChange={tune("filter_radius")}
                      hint="Only used by the harvest pitch tracker." />
                    <Field label="Pitch tracker" hint="RMVPE is the most reliable, especially for singing.">
                      <select className="input" value={p.f0_method} onChange={(e) => tune("f0_method")(e.target.value)}>
                        <option value="rmvpe">RMVPE (recommended)</option>
                        <option value="crepe">Crepe</option>
                        <option value="mangio-crepe">Mangio-Crepe</option>
                        <option value="harvest">Harvest (slow)</option>
                        <option value="pm">PM (fast, rough)</option>
                      </select>
                    </Field>
                    <Field label="File format">
                      <select className="input" value={p.format} onChange={(e) => tune("format")(e.target.value)}>
                        <option value="mp3">MP3, 320 kbps</option>
                        <option value="wav">WAV, lossless</option>
                        <option value="flac">FLAC, lossless</option>
                      </select>
                    </Field>
                  </div>
                )}
              </div>
            </div>
          </Step>
        </div>

        <aside className="card p-5 lg:sticky lg:top-20 space-y-4">
          <h2 className="font-bold text-lg">Ready to make</h2>
          <dl className="text-sm space-y-2">
            {[["Type", MODES.find((m) => m.id === mode)!.title],
              ["Source", mode === "tts" ? (text.trim() ? `${text.trim().length} characters` : "—") : file?.name ?? "—"],
              ["Voice", voice?.name ?? "—"],
              ["Pitch", semitones(p.pitch + (mode === "cover" ? p.song_key : 0))]].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4">
                <dt className="text-muted">{k}</dt>
                <dd className="truncate text-right">{v}</dd>
              </div>
            ))}
          </dl>
          <Field label="Name it (optional)">
            <input className="input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={file?.name.replace(/\.[^.]+$/, "") ?? "Untitled"} />
          </Field>

          {busy && mode !== "tts" && (
            <div className="space-y-1.5">
              <ProgressBar value={uploaded} />
              <p className="hint">{uploaded < 1 ? `Uploading… ${Math.round(uploaded * 100)}%` : "Checking the file…"}</p>
            </div>
          )}
          <ErrorNote>{error}</ErrorNote>

          <button type="button" className="btn btn-primary w-full py-2.5" disabled={busy || Boolean(missing)} onClick={submit}>
            {busy ? "Sending…" : missing ?? (mode === "cover" ? "Make the cover" : "Convert")}
          </button>

          {system && system.engine !== "ready" && (
            <p className="hint">
              {system.engine === "starting"
                ? "The engine is still starting. You can submit now; the job will wait in line."
                : "The engine is offline. Jobs will wait in line until a worker starts."}
            </p>
          )}
          {system?.engine === "ready" && system.device === "cpu" && (
            <p className="hint">Running on CPU, so expect this to take a few times the length of the audio{mode === "cover" ? ", plus time to separate the vocals" : ""}.</p>
          )}
        </aside>
      </div>
    </>
  );
}
