const BASE_URL = "/api";

let _token: string | null = sessionStorage.getItem("dvbm_token");

export function setToken(token: string | null) {
  _token = token;
  if (token) {
    sessionStorage.setItem("dvbm_token", token);
  } else {
    sessionStorage.removeItem("dvbm_token");
  }
}

export function getToken(): string | null {
  return _token;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    setToken(null);
    sessionStorage.removeItem("dvbm_auth");
    window.location.reload();
    throw new Error("Unauthorized");
  }

  if (res.status === 204) {
    return undefined as unknown as T;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
