import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, token, type System, type User } from "./api";

// -- auth ------------------------------------------------------------------

type Auth = {
  user: User | null;
  loading: boolean;
  signIn: (accessToken: string, user: User) => void;
  signOut: () => void;
};

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(token.get()));

  useEffect(() => {
    if (token.get()) {
      api.get<User>("/auth/me").then(setUser).catch(() => token.clear()).finally(() => setLoading(false));
    }
    const onSignedOut = () => setUser(null);
    window.addEventListener("voicely:signed-out", onSignedOut);
    return () => window.removeEventListener("voicely:signed-out", onSignedOut);
  }, []);

  const signIn = useCallback((accessToken: string, u: User) => {
    token.set(accessToken);
    setUser(u);
  }, []);
  const signOut = useCallback(() => {
    token.clear();
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, loading, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

// -- data ------------------------------------------------------------------

/**
 * Load `path` and keep it fresh. `interval` may depend on the data, so a list
 * can poll quickly while something is in progress and slowly otherwise.
 */
export function usePolled<T>(path: string | null, interval: (data: T | null) => number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef({ interval, data });
  latest.current = { interval, data };

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api.get<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [path]);

  useEffect(() => {
    let stopped = false;
    let timer: number;
    const tick = async () => {
      // Skip refreshes while the tab is hidden; catch up when it returns.
      if (!document.hidden) await reload();
      if (!stopped) timer = window.setTimeout(tick, latest.current.interval(latest.current.data));
    };
    tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [reload]);

  return { data, error, reload, setData };
}

export function useSystem() {
  return usePolled<System>("/system", (s) => (s?.engine === "ready" ? 20000 : 4000));
}

// -- formatting ------------------------------------------------------------

export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function minutes(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} sec`;
  const m = seconds / 60;
  return `${m < 10 ? m.toFixed(1) : Math.round(m)} min`;
}

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
