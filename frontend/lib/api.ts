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

let csrfToken = "";

async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/auth/csrf/`, {
      credentials: "include",
    });
  } catch {
    throw new Error(
      "Could not reach the API. Check BACKEND_URL on Vercel and that Railway is up.",
    );
  }
  if (!response.ok) {
    throw new Error(
      `Could not start a secure session (HTTP ${response.status}).`,
    );
  }
  const data = (await response.json()) as { csrfToken: string };
  csrfToken = data.csrfToken;
  return csrfToken;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (method !== "GET") {
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
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

export const api = {
  csrf: ensureCsrf,
  me: () => request<User>("/api/auth/me/"),
  login: (username: string, password: string) =>
    request<User>("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout/", { method: "POST" }),
  scraperStatus: () => request<ScraperStatus>("/api/scraper/status/"),
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
  phones: (query: string) => request<PhonePage>(`/api/phones/${query}`),
  phone: (id: number) => request<PhoneDetail>(`/api/phones/${id}/`),
  phoneFilters: () => request<PhoneFilters>("/api/phones/filters/"),
  usage: () => request<UsagePayload>("/api/usage/"),
  alerts: () => request<{ alerts: UsagePayload["alerts"] }>("/api/alerts/"),
  keys: () => request<{ results: KeyCard[] }>("/api/keys/"),
  rotateKey: (slug: string, apiKey: string) =>
    request<KeyCard>(`/api/keys/${slug}/`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  exportUrl: (query: string) => `${API_BASE}/api/phones/export.csv${query}`,
};

export async function downloadCsv(query: string): Promise<void> {
  const token = await ensureCsrf();
  const response = await fetch(api.exportUrl(query), {
    credentials: "include",
    headers: { "X-CSRFToken": token },
  });
  if (!response.ok) {
    throw new ApiError("Could not download the spreadsheet.", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "phone_numbers.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function clearCsrf(): void {
  csrfToken = "";
}
