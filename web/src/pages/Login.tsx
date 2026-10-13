import { useState, type FormEvent } from "react";
import { api, type User } from "../api";
import { Equalizer, ErrorNote, Field } from "../components/ui";
import { useAuth } from "../hooks";

export default function Login() {
  const { signIn } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", display_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      const res = await api.post<{ access_token: string; user: User }>(`/auth/${mode}`, body);
      signIn(res.access_token, res.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <section className="hidden lg:flex flex-col justify-between p-12 border-r border-line bg-panel">
        <span className="flex items-center gap-2 font-display font-bold text-xl">
          <Equalizer className="text-accent" /> Voicely
        </span>
        <div>
          <h1 className="text-5xl font-bold leading-[1.05]">Any song.<br />Any performance.<br /><span className="text-accent">Your voice.</span></h1>
          <p className="text-muted mt-6 max-w-md text-lg">
            Upload a song or a recording and hear it re-sung in a voice you built. The words, timing and melody stay; only the voice changes.
          </p>
        </div>
        <ol className="grid grid-cols-3 gap-6 text-sm">
          {[["Build a voice", "From 10 minutes of clean recordings, or import a model."],
            ["Pick a performance", "A full song, a spoken clip, or just typed text."],
            ["Get it back re-voiced", "Mixed, labelled as AI-made, ready to download."]].map(([t, d], i) => (
            <li key={t}>
              <span className="eyebrow">Step {i + 1}</span>
              <p className="font-medium mt-1">{t}</p>
              <p className="hint mt-1">{d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5">
          <div>
            <span className="lg:hidden flex items-center gap-2 font-display font-bold text-xl mb-8">
              <Equalizer className="text-accent" /> Voicely
            </span>
            <h2 className="text-2xl font-bold">{mode === "login" ? "Sign in" : "Create your account"}</h2>
            <p className="hint mt-1">
              {mode === "login" ? "New here? " : "Already have an account? "}
              <button type="button" className="text-accent hover:underline cursor-pointer" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
                {mode === "login" ? "Create an account" : "Sign in"}
              </button>
            </p>
          </div>

          {mode === "register" && (
            <Field label="Your name">
              <input className="input" value={form.display_name} onChange={set("display_name")} required maxLength={80} autoComplete="name" />
            </Field>
          )}
          <Field label="Email">
            <input className="input" type="email" value={form.email} onChange={set("email")} required autoComplete="email" />
          </Field>
          <Field label="Password" hint={mode === "register" ? "At least 8 characters." : undefined}>
            <input className="input" type="password" value={form.password} onChange={set("password")} required minLength={mode === "register" ? 8 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </Field>

          <ErrorNote>{error}</ErrorNote>
          <button className="btn btn-primary w-full py-2.5" disabled={busy}>
            {busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </section>
    </div>
  );
}
