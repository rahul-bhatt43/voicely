import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Voice } from "../api";
import { ErrorNote, Field, PageHeader } from "../components/ui";
import { useAuth } from "../hooks";

export default function NewVoice() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [whose, setWhose] = useState<"self" | "permission">("self");
  const [person, setPerson] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const voice = await api.post<Voice>("/voices", {
        name, description, consent_type: whose,
        consent_name: whose === "self" ? user!.display_name : person,
        consent_confirmed: confirmed,
      });
      navigate(`/voices/${voice.id}`, { replace: true });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader eyebrow="New voice" title="Whose voice is this?">
        Start with the basics and the permission. You add recordings or a model on the next screen.
      </PageHeader>

      <form onSubmit={submit} className="space-y-6">
        <div className="card p-6 space-y-5">
          <Field label="Voice name" hint="How it appears when you pick a voice.">
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} placeholder="e.g. My singing voice" />
          </Field>
          <Field label="Description (optional)">
            <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} placeholder="Warm baritone, recorded on a condenser mic" />
          </Field>
        </div>

        <fieldset className="card p-6 space-y-4">
          <legend className="sr-only">Permission</legend>
          <h2 className="font-bold text-lg">Permission</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {([["self", "It's my own voice", "I'm the person in the recordings."],
               ["permission", "Someone else's voice", "They agreed to have their voice cloned."]] as const).map(([value, title, sub]) => (
              <label key={value} className={`rounded-xl border p-4 cursor-pointer transition-colors ${whose === value ? "border-accent bg-accent/10" : "border-line hover:border-muted"}`}>
                <input type="radio" name="whose" className="sr-only" checked={whose === value} onChange={() => setWhose(value)} />
                <span className="block font-medium">{title}</span>
                <span className="hint">{sub}</span>
              </label>
            ))}
          </div>

          {whose === "permission" && (
            <Field label="Their full name" hint="Kept with the voice as the record of who gave permission.">
              <input className="input" value={person} onChange={(e) => setPerson(e.target.value)} required minLength={2} maxLength={120} />
            </Field>
          )}

          <label className="flex gap-3 items-start cursor-pointer">
            <input type="checkbox" className="mt-1 size-4 accent-accent" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            <span className="text-sm">
              {whose === "self"
                ? "I confirm this is my own voice and I'm choosing to make a model of it."
                : "I confirm this person knows their voice is being cloned and has clearly agreed to it."}
              <span className="hint block mt-1">
                Cloning a voice without permission, including a celebrity's or public figure's, isn't allowed here. Your confirmation is saved with the date.
              </span>
            </span>
          </label>
        </fieldset>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex gap-2">
          <button className="btn btn-primary" disabled={busy || !confirmed}>{busy ? "Creating…" : "Continue"}</button>
          <Link to="/voices" className="btn btn-ghost">Cancel</Link>
        </div>
      </form>
    </div>
  );
}
