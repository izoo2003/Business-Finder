import type {
  KeyCard,
  PhoneDetail,
  PhoneFilters,
  PhonePage,
  ScraperStatus,
  UsagePayload,
  User,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.trim() ||
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");

const ME_TTL_MS = 60_000;
const FILTERS_TTL_MS = 120_000;

let csrfToken = "";
let meCache: { user: User; at: number } | null = null;
let filtersCache: { data: PhoneFilters; at: number } | null = null;

function readCsrfCookie(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function fetchCsrfToken(): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/auth/csrf/`, {
      credentials: "include",
    });
  } catch {
    throw new Error(
      "Could not reach the API. Redeploy Vercel after setting BACKEND_URL, and confirm Railway is online.",
    );
  }
  if (!response.ok) {
    let detail = `Could not start a secure session (HTTP ${response.status}).`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (typeof data.detail === "string" && data.detail) {
        detail = data.detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const data = (await response.json()) as { csrfToken: string };
  // Prefer the cookie Django just set — it must match what middleware checks.
  csrfToken = readCsrfCookie() || data.csrfToken;
  return csrfToken;
}

async function ensureCsrf(force = false): Promise<string> {
  if (!force) {
    const fromCookie = readCsrfCookie();
    if (fromCookie) {
      csrfToken = fromCookie;
      return fromCookie;
    }
    if (csrfToken) return csrfToken;
  }
  return fetchCsrfToken();
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function isCsrfFailure(status: number, detail: string): boolean {
  if (status !== 403) return false;
  const lower = detail.toLowerCase();
  return lower.includes("csrf");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retried = false,
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (method !== "GET" && method !== "HEAD") {
    headers.set("X-CSRFToken", await ensureCsrf());
    if (!headers.has("Content-Type") && options.body) {
      headers.set("Content-Type", "application/json");
    }
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    credentials: "include",
    headers,
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) {
      throw new ApiError("Something went wrong. Try again.", response.status);
    }
    return response as T;
  }
  const data = await response.json();
  if (!response.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : "Something went wrong. Try again.";
    if (!retried && isCsrfFailure(response.status, detail)) {
      csrfToken = "";
      await ensureCsrf(true);
      return request<T>(path, options, true);
    }
    throw new ApiError(detail, response.status);
  }
  // Keep memory in sync if login/session rotated the cookie.
  const fresh = readCsrfCookie();
  if (fresh) csrfToken = fresh;
  return data as T;
}

async function loadMe(): Promise<User> {
  const now = Date.now();
  if (meCache && now - meCache.at < ME_TTL_MS) {
    return meCache.user;
  }
  const user = await request<User>("/api/auth/me/");
  meCache = { user, at: now };
  return user;
}

async function loadPhoneFilters(signal?: AbortSignal): Promise<PhoneFilters> {
  const now = Date.now();
  if (filtersCache && now - filtersCache.at < FILTERS_TTL_MS) {
    return filtersCache.data;
  }
  const data = await request<PhoneFilters>("/api/phones/filters/", { signal });
  filtersCache = { data, at: now };
  return data;
}

export const api = {
  csrf: () => ensureCsrf(),
  me: loadMe,
  login: async (username: string, password: string) => {
    const user = await request<User>("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    // Login rotates the CSRF cookie — drop the pre-login token.
    csrfToken = readCsrfCookie();
    if (!csrfToken) {
      await ensureCsrf(true);
    }
    meCache = { user, at: Date.now() };
    return user;
  },
  logout: async () => {
    const result = await request<{ ok: boolean }>("/api/auth/logout/", {
      method: "POST",
    });
    clearSessionCache();
    return result;
  },
  scraperStatus: (signal?: AbortSignal) =>
    request<ScraperStatus>("/api/scraper/status/", { signal }),
  scraperStart: () =>
    request<ScraperStatus>("/api/scraper/start/", { method: "POST" }),
  scraperStop: () =>
    request<ScraperStatus>("/api/scraper/stop/", { method: "POST" }),
  scraperUpdateOrchestration: (payload: {
    cities: string[];
    categories: string[];
  }) =>
    request<ScraperStatus>("/api/scraper/orchestration/", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  phones: (query: string, signal?: AbortSignal) =>
    request<PhonePage>(`/api/phones/${query}`, { signal }),
  phone: (id: number, signal?: AbortSignal) =>
    request<PhoneDetail>(`/api/phones/${id}/`, { signal }),
  phoneFilters: loadPhoneFilters,
  usage: (signal?: AbortSignal) =>
    request<UsagePayload>("/api/usage/", { signal }),
  alerts: (signal?: AbortSignal) =>
    request<{ alerts: UsagePayload["alerts"] }>("/api/alerts/", { signal }),
  keys: () => request<{ results: KeyCard[] }>("/api/keys/"),
  rotateKey: (slug: string, apiKey: string) =>
    request<KeyCard>(`/api/keys/${slug}/`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  exportUrl: (query: string) => `${API_BASE}/api/phones/export.csv${query}`,
};

export async function downloadCsv(query: string): Promise<void> {
  const stamp = new Date().toISOString().slice(0, 16).replace("T", "_").replace(":", "");
  const filename = `phone_numbers_${stamp}.csv`;

  async function saveBlob(blob: Blob) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  const token = await ensureCsrf();
  const response = await fetch(api.exportUrl(query), {
    credentials: "include",
    headers: { "X-CSRFToken": token },
  });
  if (!response.ok) {
    if (response.status === 403) {
      csrfToken = "";
      const retryToken = await ensureCsrf(true);
      const retry = await fetch(api.exportUrl(query), {
        credentials: "include",
        headers: { "X-CSRFToken": retryToken },
      });
      if (!retry.ok) {
        throw new ApiError("Could not download the spreadsheet.", retry.status);
      }
      await saveBlob(await retry.blob());
      return;
    }
    throw new ApiError("Could not download the spreadsheet.", response.status);
  }
  await saveBlob(await response.blob());
}

/** Clear CSRF + cached session data (call on sign-out). */
export function clearSessionCache(): void {
  csrfToken = "";
  meCache = null;
  filtersCache = null;
}
