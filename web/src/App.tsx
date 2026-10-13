import { LogOut } from "lucide-react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import type { System } from "./api";
import { Equalizer, Spinner } from "./components/ui";
import { useAuth, useSystem } from "./hooks";
import Create from "./pages/Create";
import Guide from "./pages/Guide";
import Library from "./pages/Library";
import Login from "./pages/Login";
import NewVoice from "./pages/NewVoice";
import VoiceDetail from "./pages/VoiceDetail";
import Voices from "./pages/Voices";

const NAV = [
  { to: "/", label: "Create" },
  { to: "/library", label: "Library" },
  { to: "/voices", label: "Voices" },
  { to: "/guide", label: "Guide" },
];

function EngineStatus({ system }: { system: System | null }) {
  if (!system) return null;
  const view = {
    ready: { dot: "bg-good", text: system.device === "gpu" ? "Engine ready · GPU" : "Engine ready · CPU" },
    starting: { dot: "bg-warn animate-pulse", text: "Engine starting…" },
    offline: { dot: "bg-bad", text: "Engine offline" },
  }[system.engine];
  const title =
    system.engine === "ready"
      ? system.gpu ?? "Running on CPU: conversions work but take a few times the length of the audio."
      : system.engine === "starting"
        ? "The worker is loading models. The first start downloads about 1 GB."
        : "No worker is connected. Jobs will wait in the queue until one starts.";
  return (
    <span className="hidden md:inline-flex items-center gap-2 text-[13px] text-muted" title={title}>
      <span className={`size-2 rounded-full ${view.dot}`} />
      {view.text}
    </span>
  );
}

export default function App() {
  const { user, loading, signOut } = useAuth();

  if (loading) {
    return <div className="min-h-screen grid place-items-center"><Spinner className="size-6 text-muted" /></div>;
  }
  if (!user) return <Login />;
  return <Shell name={user.display_name} onSignOut={signOut} />;
}

function Shell({ name, onSignOut }: { name: string; onSignOut: () => void }) {
  const { data: system } = useSystem();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-ink/85 backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 h-14 flex items-center gap-2 sm:gap-6">
          <NavLink to="/" className="flex items-center gap-2 font-display font-bold text-lg">
            <Equalizer active={false} className="text-accent" /> <span className="hidden sm:inline">Voicely</span>
          </NavLink>
          <nav className="flex gap-1 flex-1 overflow-x-auto">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) => `rounded-lg px-2 sm:px-3 py-1.5 text-sm font-medium transition-colors ${isActive ? "bg-raised text-text" : "text-muted hover:text-text"}`}
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <EngineStatus system={system} />
          <span className="hidden sm:block text-sm text-muted truncate max-w-32">{name}</span>
          <button type="button" className="btn btn-ghost px-2" onClick={onSignOut} aria-label="Sign out" title="Sign out">
            <LogOut className="size-4" />
          </button>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-4 sm:px-6 py-10">
        <Routes>
          <Route path="/" element={<Create system={system} />} />
          <Route path="/library" element={<Library />} />
          <Route path="/voices" element={<Voices />} />
          <Route path="/voices/new" element={<NewVoice />} />
          <Route path="/voices/:id" element={<VoiceDetail system={system} />} />
          <Route path="/guide" element={<Guide />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="border-t border-line">
        <p className="mx-auto max-w-6xl px-4 sm:px-6 py-5 hint">
          Every file made here is labelled as AI-generated. Only clone a voice you own or have clear permission to use.
        </p>
      </footer>
    </div>
  );
}
