import { Plus, Users } from "lucide-react";
import { Link } from "react-router-dom";
import type { Voice } from "../api";
import { Chip, Empty, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { VoiceAvatar } from "../components/VoicePicker";
import { usePolled } from "../hooks";

const BUSY = (v: Voice) => v.status === "training" || v.status === "validating";

export function VoiceStatusChip({ voice }: { voice: Voice }) {
  switch (voice.status) {
    case "ready": return <Chip tone="good">Ready</Chip>;
    case "training": return <Chip tone="accent">Training</Chip>;
    case "validating": return <Chip tone="accent">Checking</Chip>;
    case "failed": return <Chip tone="bad">Needs attention</Chip>;
    default: return <Chip>Not built yet</Chip>;
  }
}

function VoiceCard({ voice }: { voice: Voice }) {
  return (
    <Link to={`/voices/${voice.id}`} className="card p-5 flex gap-4 min-w-0 hover:border-muted transition-colors">
      <VoiceAvatar voice={voice} size="size-12" />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-bold text-lg truncate">{voice.name}</h3>
          <VoiceStatusChip voice={voice} />
        </div>
        <p className="hint line-clamp-2 mt-0.5">
          {voice.description || (voice.is_owner ? "No description." : `Shared by ${voice.owner_name}.`)}
        </p>
        {voice.is_owner && voice.visibility === "public" && (
          <p className="hint flex items-center gap-1 mt-2"><Users className="size-3" /> Shared with everyone here</p>
        )}
      </div>
    </Link>
  );
}

export default function Voices() {
  const { data: voices, error } = usePolled<Voice[]>("/voices", (list) => (list?.some(BUSY) ? 3000 : 20000));
  const mine = voices?.filter((v) => v.is_owner) ?? [];
  const shared = voices?.filter((v) => !v.is_owner) ?? [];

  return (
    <>
      <PageHeader eyebrow="Voices" title="Your voice models"
        action={<Link to="/voices/new" className="btn btn-primary"><Plus className="size-4" /> New voice</Link>}>
        A voice is a small model of how one person sounds. Build one from recordings, or import one you trained elsewhere.
      </PageHeader>

      <ErrorNote>{error}</ErrorNote>
      {!voices && !error && <Spinner className="size-5 text-muted" />}

      {voices && mine.length === 0 && (
        <Empty title="No voices yet"
          action={<div className="flex justify-center gap-2">
            <Link to="/voices/new" className="btn btn-primary">Create your first voice</Link>
            <Link to="/guide" className="btn btn-secondary">Read the guide</Link>
          </div>}>
          You need about 10 minutes of clean recordings of one person, and that person's permission.
        </Empty>
      )}

      {mine.length > 0 && <div className="grid grid-cols-1 gap-4 md:grid-cols-2">{mine.map((v) => <VoiceCard key={v.id} voice={v} />)}</div>}

      {shared.length > 0 && (
        <section className="mt-12">
          <h2 className="eyebrow mb-3">Shared by others on this server</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">{shared.map((v) => <VoiceCard key={v.id} voice={v} />)}</div>
        </section>
      )}
    </>
  );
}
