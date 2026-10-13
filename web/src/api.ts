const TOKEN_KEY = "voicely.token";

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

/** FastAPI sends `detail` as a string, or as a list of field errors. */
function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
  }
  if (status === 413) return "That file is too large.";
  if (status >= 500) return "The server had a problem. Please try again.";
  return `Request failed (${status}).`;
}

function fail(status: number, body: unknown): never {
  if (status === 401 && token.get()) {
    token.clear();
    window.dispatchEvent(new Event("voicely:signed-out"));
  }
  throw new ApiError(messageFrom(body, status), status);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError("Can't reach the server. Is it running?", 0);
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) fail(res.status, data);
  return data as T;
}

/** Multipart upload with progress; fetch cannot report upload progress. */
function upload<T>(path: string, form: FormData, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api${path}`);
    const t = token.get();
    if (t) xhr.setRequestHeader("Authorization", `Bearer ${t}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError("The upload was interrupted.", 0));
    xhr.onload = () => {
      let data: unknown = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* non-JSON error page */ }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as T);
      try { fail(xhr.status, data); } catch (e) { reject(e); }
    };
    xhr.send(form);
  });
}

async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${token.get()}` } });
  if (!res.ok) fail(res.status, await res.json().catch(() => null));
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: (path: string) => request<void>("DELETE", path),
  upload,
  download,
};

// -- types (mirrors api/app/schemas.py) -------------------------------------

export type User = { id: string; email: string; display_name: string };

export type Issue = { level: "warn" | "bad"; text: string };

export type DatasetFile = {
  id: string;
  filename: string;
  duration: number;
  url: string;
  analysis: { voiced_seconds: number; peak_db: number | null; rms_db: number | null; issues: Issue[] };
};

export type DatasetSummary = {
  files: number;
  seconds: number;
  voiced_seconds: number;
  flagged: number;
  level: "low" | "ok" | "good";
  text: string;
  min_seconds: number;
  good_seconds: number;
};

export type VoiceStatus = "draft" | "validating" | "training" | "ready" | "failed";

export type Voice = {
  id: string;
  name: string;
  description: string;
  status: VoiceStatus;
  status_detail: string;
  visibility: "private" | "public";
  source: "upload" | "trained" | null;
  is_owner: boolean;
  owner_name: string;
  has_index: boolean;
  meta: { sample_rate?: number; version?: string; epochs?: number; clips?: number };
  created_at: string;
  consent?: { type: "self" | "permission"; name: string; at: string; has_audio: boolean };
  dataset?: DatasetFile[];
  dataset_summary?: DatasetSummary;
};

export type JobType = "convert" | "cover" | "tts" | "train";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export type Job = {
  id: string;
  type: JobType;
  title: string;
  status: JobStatus;
  progress: number;
  stage: string;
  error: string;
  log: string;
  voice_id: string | null;
  voice_name: string;
  params: Record<string, unknown>;
  meta: { input_seconds?: number };
  outputs: Record<string, { url: string; download_url: string }>;
  input_url: string | null;
  created_at: string;
  finished_at: string | null;
  seconds: number | null;
};

export type System = {
  engine: "ready" | "starting" | "offline";
  device: "gpu" | "cpu" | null;
  gpu: string | null;
  can_train: boolean;
  queued: number;
  busy: number;
  tts_voices: { id: string; label: string }[];
  limits: { max_upload_mb: number; max_audio_minutes: number; max_tts_chars: number; max_dataset_minutes: number };
};

export const isActive = (j: Job) => j.status === "queued" || j.status === "running";
