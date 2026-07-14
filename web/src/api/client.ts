/** Dunne fetch-laag. 502 (intervals.icu down) krijgt een eigen error-type
 *  zodat de UI cached data + offline-banner kan tonen. */

const TOKEN_KEY = "api_token";

/** Vuurt zodra een request 401 geeft: de sessie is weg. App.tsx luistert
 *  en schakelt terug naar het inlogscherm. */
export const AUTH_LOST_EVENT = "coach:auth-lost";

/** Eenmalig: ?token=xxx in de URL → localStorage, daarna URL opschonen.
 *  Zo koppel je de PWA aan een gedeployde backend zonder login-UI. */
(() => {
  try {
    const url = new URL(window.location.href);
    const t = url.searchParams.get("token");
    if (t) {
      localStorage.setItem(TOKEN_KEY, t);
      url.searchParams.delete("token");
      window.history.replaceState(null, "", url.toString());
    }
  } catch {
    /* SSR/test-omgeving zonder window */
  }
})();

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const token = getToken();
  try {
    res = await fetch(path, {
      ...init,
      // De sessie-cookie is httpOnly: JS ziet 'm niet, maar moet 'm wel
      // meesturen. Zonder dit blijft elke request 401 na een geslaagde login.
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    // Netwerk helemaal weg (en niets in de SW-cache).
    throw new ApiError(0, "offline");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* geen JSON-body */
    }
    // Sessie verlopen of ingetrokken tijdens gebruik: de app moet terug naar
    // het inlogscherm, niet elk scherm apart een foutmelding laten tonen.
    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new Event(AUTH_LOST_EVENT));
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const get = <T>(path: string) => request<T>(path);

export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const put = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "PUT",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const del = <T>(path: string) =>
  request<T>(path, {
    method: "DELETE",
  });

/** Niet bereikbaar: echt offline of backend meldt 502 (intervals.icu). */
export function isUnavailable(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 0 || err.status === 502);
}

/** 401 — niet ingelogd. De app toont dan het inlogscherm. */
export function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

// ── auth ───────────────────────────────────────────────────────────────────

export type AuthStatus = { authenticated: boolean; auth_required: boolean };

export const getAuthStatus = () => get<AuthStatus>("/api/auth/status");

/** Zet de httpOnly sessie-cookie. Gooit ApiError(401) bij fout wachtwoord,
 *  ApiError(429) als de brute-force-rem aanslaat. */
export const login = (password: string) =>
  post<{ ok: boolean }>("/api/auth/login", { password });

export async function logout(): Promise<void> {
  await post("/api/auth/logout");
  setToken(null); // ook de oude bearer-token opruimen
}
