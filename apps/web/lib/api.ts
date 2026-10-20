export const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export type ApiError = Error & { status?: number };

export function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("bazaar_token");
}

export function setToken(value: string | null) {
  if (value) localStorage.setItem("bazaar_token", value);
  else localStorage.removeItem("bazaar_token");
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const session = token();
  if (session) headers.set("Authorization", `Bearer ${session}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = new Error(body?.detail || response.statusText) as ApiError;
    error.status = response.status;
    throw error;
  }
  return body as T;
}
