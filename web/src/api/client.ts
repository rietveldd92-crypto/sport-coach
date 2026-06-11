/** Dunne fetch-laag. 502 (intervals.icu down) krijgt een eigen error-type
 *  zodat de UI cached data + offline-banner kan tonen. */

const TOKEN_KEY = "api_token";

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
    throw new ApiError(res.status, detail);
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

/** Niet bereikbaar: echt offline of backend meldt 502 (intervals.icu). */
export function isUnavailable(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 0 || err.status === 502);
}

/** 401 — token ontbreekt of klopt niet (open de app met ?token=…). */
export function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
