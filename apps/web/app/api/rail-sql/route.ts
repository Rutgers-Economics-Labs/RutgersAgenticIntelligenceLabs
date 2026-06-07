/**
 * Proxy for the RAIL SQL endpoint.
 * srcdoc iframes inherit the parent origin (localhost:3000) and can call
 * this route as a same-origin request, avoiding CORS issues with the
 * FastAPI backend.
 */
const API_ROOT =
  process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  const body = await request.json();
  const referer = request.headers.get("referer");
  const projectSlug = extractProjectSlug(referer);
  const target = new URL(`${API_ROOT}/sql`);
  if (projectSlug) {
    target.searchParams.set("projectSlug", projectSlug);
  }
  const res = await fetch(target, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  const normalized = normalizeSqlPayload(data);
  return Response.json(normalized, { status: res.status });
}

function extractProjectSlug(referer: string | null): string | null {
  if (!referer) return null;
  try {
    const url = new URL(referer);
    const parts = url.pathname.split("/").filter(Boolean);
    const projectIndex = parts.indexOf("projects");
    if (projectIndex >= 0 && parts[projectIndex + 1]) {
      return parts[projectIndex + 1];
    }
  } catch {}
  return null;
}

function normalizeSqlPayload(data: any) {
  if (!data || !Array.isArray(data.columns) || !Array.isArray(data.rows)) {
    return data;
  }
  if (data.rows.length > 0 && !Array.isArray(data.rows[0]) && typeof data.rows[0] === "object") {
    return {
      ...data,
      rows: data.rows.map((row: Record<string, unknown>) => data.columns.map((column: string) => row[column])),
    };
  }
  return data;
}

export async function OPTIONS() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
