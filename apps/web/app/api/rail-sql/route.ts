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
  const res = await fetch(`${API_ROOT}/sql`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return Response.json(data);
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
