/** JSON calls to BrainSync's REST routes. Paths are relative ("api/..."): the page may sit under a proxy prefix. */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** 401: no login, or it expired. */
export class UnauthorizedError extends ApiError {}

const TOKEN_KEY = "brainsync.token";
let unauthorizedHandler: (() => void) | null = null;

export function getToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage blocked: the login lasts until reload */ }
}

/** Called on every 401 (the session store uses it to send the user back to Login). */
export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler;
}

/** FastAPI errors: `detail` is a string, or a list of field errors (422). */
function messageOf(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((d) => (d as { msg?: unknown } | null)?.msg).filter((m): m is string => typeof m === "string");
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}

export type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";
export interface RequestOptions {
  /** Send this file as the raw request body (pack upload). */
  raw?: Blob;
  /** Return the response body as a Blob (pack download). */
  blob?: boolean;
}

export async function apiRequest<T>(method: HttpMethod, path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const init: RequestInit = { method, headers };
  if (options.raw) {
    headers["Content-Type"] = "application/octet-stream";
    init.body = options.raw;
  } else if (method === "POST" || body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body ?? {});
  }
  const response = await fetch(path, init);
  if (response.ok && options.blob) return (await response.blob()) as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message = messageOf(data, response.statusText || `HTTP ${response.status}`);
    if (response.status === 401 && path !== "api/auth/login") {
      unauthorizedHandler?.();
      throw new UnauthorizedError(401, message);
    }
    throw new ApiError(response.status, message);
  }
  return data as T;
}
