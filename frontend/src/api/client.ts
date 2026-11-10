export type ApiRole = "analyst" | "supervisor" | "admin";

export interface DatasetRecord { id: string; filename: string; created_at: string; metadata: string }
export interface ApiModel { modele_cible: string; rows: number; eligible: number; defaults: number }
export interface ApiRun { id: string; run_type: string; model: string | null; created_at: string; created_by: string; result: string }

const API_URL = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) { super(message); }
}

async function request<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Le service est momentanément indisponible. Réessayez plus tard ou contactez l’administrateur.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(body.detail ?? "Erreur API", response.status);
  return body as T;
}

export const api = {
  login: (username: string, password: string) => request<{ access_token: string }>("/auth/login", undefined, { method: "POST", body: JSON.stringify({ username, password }) }),
  register: (username: string, fullName: string, email: string, password: string) => request<{ message: string }>("/auth/register", undefined, { method: "POST", body: JSON.stringify({ username, full_name: fullName, email, password }) }),
  datasets: (token: string) => request<DatasetRecord[]>("/datasets", token),
  models: (token: string, datasetId: string) => request<{ models: ApiModel[] }>(`/datasets/${datasetId}/models`, token),
  upload: (token: string, file: File, performanceDate?: string, actualRatingColumn?: string) => {
    const form = new FormData();
    form.set("file", file);
    if (performanceDate) form.set("performance_date", performanceDate);
    if (actualRatingColumn) form.set("actual_rating_column", actualRatingColumn);
    return request<{ dataset_id: string; preparation_report: Record<string, unknown> }>("/datasets", token, { method: "POST", body: form });
  },
  backtest: (token: string, datasetId: string, model: string, horizon: { developmentStart: string; developmentEnd: string; backtestStart: string; backtestEnd: string }) => request<Record<string, unknown>>("/workflows/backtesting", token, { method: "POST", body: JSON.stringify({ dataset_id: datasetId, model, development_start: horizon.developmentStart, development_end: horizon.developmentEnd, backtest_start: horizon.backtestStart, backtest_end: horizon.backtestEnd }) }),
  chat: (token: string, question: string, runId?: string, model?: string) => request<{ answer: string; guardrail?: string; references?: { type: string; value: string }[] }>("/assistant/chat", token, { method: "POST", body: JSON.stringify({ question, run_id: runId ?? null, model: model ?? null }) }),
  runs: (token: string) => request<ApiRun[]>("/runs", token),
};

export function userFromToken(token: string): { username: string; role: ApiRole } | null {
  try {
    const payload = token.split(".")[1];
    const data = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    if (["analyst", "supervisor", "admin"].includes(data.role) && data.sub) return { username: data.sub, role: data.role };
  } catch { /* token is validated by the API on each request */ }
  return null;
}
