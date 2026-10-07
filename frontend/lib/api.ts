import { createClient } from "./supabase";

const BASE = process.env.NEXT_PUBLIC_API_URL!;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function messageFrom(data: unknown, status: number): string {
  const d = (data as { detail?: unknown })?.detail ?? data;
  if (typeof d === "string" && d.length < 400) return d;
  if (Array.isArray(d)) {
    return d.map((e: { loc?: string[]; msg?: string }) => `${e.loc?.at(-1) ?? "field"}: ${e.msg}`).join(". ");
  }
  return `Request failed (${status})`;
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const { data } = await createClient().auth.getSession();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (data.session) headers.Authorization = `Bearer ${data.session.access_token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. It may be waking up, so try again in a few seconds.");
  }

  const text = await res.text();
  let parsed: unknown = null;
  try { parsed = text ? JSON.parse(text) : null; } catch { parsed = text; }
  if (!res.ok) throw new ApiError(res.status, messageFrom(parsed, res.status));
  return parsed as T;
}

export const apiGet = <T>(path: string) => api<T>(path);
export const apiPost = <T>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body ?? {} });
export const apiPatch = <T>(path: string, body?: unknown) => api<T>(path, { method: "PATCH", body });
export const apiDelete = <T>(path: string) => api<T>(path, { method: "DELETE" });