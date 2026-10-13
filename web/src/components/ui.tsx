import { AlertTriangle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function Spinner({ className = "" }: { className?: string }) {
  return <Loader2 className={`size-4 animate-spin ${className}`} aria-hidden />;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <div role="alert" className="flex gap-2 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
      <AlertTriangle className="size-4 mt-0.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="hint block mt-1.5">{hint}</span>}
    </label>
  );
}

/** A labelled slider that always shows its current value. */
export function Range(props: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}) {
  const { label, hint, value, format = String, onChange, ...range } = props;
  return (
    <label className="block">
      <span className="flex items-baseline justify-between mb-2">
        <span className="text-sm font-medium">{label}</span>
        <span className="font-mono text-[13px] text-accent tabular-nums">{format(value)}</span>
      </span>
      <input type="range" value={value} onChange={(e) => onChange(Number(e.target.value))} {...range} />
      {hint && <span className="hint block mt-1.5">{hint}</span>}
    </label>
  );
}

export function ProgressBar({ value, tone = "accent" }: { value: number; tone?: "accent" | "good" }) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className="h-1.5 rounded-full bg-line overflow-hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div
        className={`h-full rounded-full transition-[width] duration-700 ${tone === "good" ? "bg-good" : "bg-accent"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

const TONES = {
  neutral: "border-line text-muted",
  accent: "border-accent/40 text-accent bg-accent/10",
  good: "border-good/40 text-good bg-good/10",
  warn: "border-warn/40 text-warn bg-warn/10",
  bad: "border-bad/40 text-bad bg-bad/10",
};

export function Chip({ tone = "neutral", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[12px] font-medium whitespace-nowrap ${TONES[tone]}`}>
      {children}
    </span>
  );
}

/** Animated level bars: the app's "something is being sung" mark. */
export function Equalizer({ active = true, className = "" }: { active?: boolean; className?: string }) {
  return (
    <span className={`inline-flex items-end gap-[3px] h-4 ${className}`} aria-hidden>
      {[0, 0.25, 0.5, 0.15].map((delay, i) => (
        <span
          key={i}
          className={`w-[3px] h-full rounded-full bg-current ${active ? "eq-bar" : "scale-y-[0.4] origin-bottom"}`}
          style={{ animationDelay: `${delay}s` }}
        />
      ))}
    </span>
  );
}

export function PageHeader({ eyebrow, title, children, action }: { eyebrow?: string; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 mb-8">
      <div className="max-w-2xl">
        {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
        <h1 className="text-3xl sm:text-4xl font-bold">{title}</h1>
        {children && <p className="text-muted mt-2">{children}</p>}
      </div>
      {action}
    </header>
  );
}

export function Empty({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="card border-dashed px-6 py-12 text-center">
      <h3 className="text-lg font-bold">{title}</h3>
      <p className="text-muted mt-1 max-w-md mx-auto">{children}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
