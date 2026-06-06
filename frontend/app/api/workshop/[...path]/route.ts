export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const INTERNAL_API_BASE = process.env.INTERNAL_API_URL || API_BASE;

function buildTargetURL(path: string[], requestURL: string): string {
  const url = new URL(requestURL);
  const target = new URL(`/api/workshop/${path.join("/")}`, INTERNAL_API_BASE);
  target.search = url.search;
  return target.toString();
}

function buildForwardHeaders(request: Request): Headers {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  return headers;
}

function buildResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const cacheControl = response.headers.get("cache-control");
  if (cacheControl) headers.set("cache-control", cacheControl);
  return headers;
}

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const targetURL = buildTargetURL(path, request.url);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();

  const response = await fetch(targetURL, {
    method: request.method,
    headers: buildForwardHeaders(request),
    body,
    cache: "no-store",
  });

  return new Response(response.body, {
    status: response.status,
    headers: buildResponseHeaders(response),
  });
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function PUT(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function DELETE(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
