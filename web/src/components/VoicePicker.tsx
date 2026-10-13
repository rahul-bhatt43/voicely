import { Check, Plus, Users } from "lucide-react";
import { Link } from "react-router-dom";
import type { Voice } from "../api";

/** Stable per-voice colour, so a voice is recognisable across the app. */
export function voiceHue(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

export function VoiceAvatar({ voice, size = "size-10" }: { voice: Pick<Voice, "id" | "name">; size?: string }) {
  const hue = voiceHue(voice.id);
  return (
    <span
      className={`${size} shrink-0 rounded-full grid place-items-center font-display font-bold text-ink`}
      style={{ background: `linear-gradient(135deg, hsl(${hue} 85% 68%), hsl(${(hue + 50) % 360} 80% 58%))` }}
      aria-hidden
    >
      {voice.name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}

export function VoicePicker({ voices, value, onChange }: {
  voices: Voice[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  const ready = voices.filter((v) => v.status === "ready");

  if (ready.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line px-5 py-8 text-center">
        <p className="font-medium">No voices yet</p>
        <p className="hint mt-1 max-w-sm mx-auto">
          A voice is a small model of how one person sounds. Build one from recordings or import one you already trained.
        </p>
        <Link to="/voices/new" className="btn btn-primary mt-4"><Plus className="size-4" /> Add a voice</Link>
      </div>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Voice">
      {ready.map((v) => {
        const selected = v.id === value;
        return (
          <button
            key={v.id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(v.id)}
            className={`flex items-center gap-3 rounded-xl border p-3 text-left transition-colors cursor-pointer ${selected ? "border-accent bg-accent/10" : "border-line bg-ink hover:border-muted"}`}
          >
            <VoiceAvatar voice={v} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{v.name}</span>
              <span className="hint flex items-center gap-1 truncate">
                {v.is_owner ? "Your voice" : <><Users className="size-3" /> Shared by {v.owner_name}</>}
              </span>
            </span>
            {selected && <Check className="size-4 text-accent shrink-0" aria-hidden />}
          </button>
        );
      })}
      <Link to="/voices/new" className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-line p-3 text-sm text-muted hover:text-text hover:border-muted transition-colors">
        <Plus className="size-4" /> Add a voice
      </Link>
    </div>
  );
}
