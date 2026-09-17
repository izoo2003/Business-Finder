import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

function backendBase(): string {
  const raw =
    process.env.BACKEND_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "";
  return raw.replace(/\/$/, "");
}

function targetUrl(req: NextRequest, pathParts: string[]): string {
  const base = backendBase();
  if (!base) {
    throw new Error("BACKEND_URL is not set");
  }
  // Always use a trailing slash so Django APPEND_SLASH does not 301-loop
  // through the Vercel proxy.
  const joined = pathParts.filter(Boolean).join("/");
  const path = joined ? `/api/${joined}/` : `/api/`;
  const search = new URL(req.url).search;
  return `${base}${path}${search}`;
}

async function proxy(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  let base: string;
  try {
    base = backendBase();
    if (!base) {
      return NextResponse.json(
        {
          detail:
            "BACKEND_URL is not set on Vercel. Add it and redeploy Production.",
        },
        { status: 500 },
      );
    }
  } catch {
    return NextResponse.json(
      { detail: "BACKEND_URL is not set on Vercel." },
      { status: 500 },
    );
  }

  const { path } = await context.params;
  // Special-case export.csv — must not get a trailing slash.
  const last = path[path.length - 1] || "";
  const isExport = last === "export.csv" || last.endsWith(".csv");
  const url = isExport
    ? `${base}/api/${path.filter(Boolean).join("/")}${new URL(req.url).search}`
    : targetUrl(req, path);

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  headers.set("accept-encoding", "identity");
  // So Django treats the proxied call as HTTPS and skips SSL redirects.
  headers.set("x-forwarded-proto", "https");
  headers.set("x-forwarded-host", req.headers.get("host") || "");

  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch {
    return NextResponse.json(
      {
        detail: `Could not reach Railway at ${base}. Check BACKEND_URL and that the web service is online.`,
      },
      { status: 502 },
    );
  }

  // Follow one absolute redirect server-side (never return relative Location
  // to the browser — that re-enters Vercel and loops).
  if (upstream.status >= 300 && upstream.status < 400) {
    const location = upstream.headers.get("location");
    if (location) {
      const absolute = new URL(location, url).toString();
      try {
        upstream = await fetch(absolute, init);
      } catch {
        return NextResponse.json(
          { detail: "Upstream redirect failed." },
          { status: 502 },
        );
      }
    }
  }

  const outHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (HOP_BY_HOP.has(lower)) return;
    if (lower === "location") return;
    outHeaders.append(key, value);
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: outHeaders,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function OPTIONS(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
