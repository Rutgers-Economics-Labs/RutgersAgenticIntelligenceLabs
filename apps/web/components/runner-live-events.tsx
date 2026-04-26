"use client";

import { useEffect, useRef, useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

interface NormalizedEvent {
  event_type: string;
  session_id: string;
  normalized_payload: Record<string, unknown>;
  debug_visibility: boolean;
}

function eventLabel(e: NormalizedEvent): string {
  const t = e.event_type.replace(/_/g, " ");
  const p = e.normalized_payload;
  const summary = p.summary ?? p.content ?? p.message ?? p.label ?? "";
  return summary ? `${t} — ${String(summary).slice(0, 120)}` : t;
}

function eventColor(eventType: string): string {
  if (eventType.includes("fail") || eventType.includes("error")) return "var(--s-failed)";
  if (eventType.includes("complet") || eventType.includes("success")) return "var(--s-running)";
  if (eventType.includes("approv") || eventType.includes("question")) return "var(--s-awaiting)";
  if (eventType.includes("verif")) return "var(--s-review)";
  return "var(--muted)";
}

export function RunnerLiveEvents({
  runner,
  sessionId,
  initialEvents = [],
}: {
  runner: string;
  sessionId: string;
  initialEvents?: NormalizedEvent[];
}) {
  const [events, setEvents] = useState<NormalizedEvent[]>(initialEvents);
  const [lastFetch, setLastFetch] = useState<string>("");
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [polling, setPolling] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!polling) return;
    let cancelled = false;

    async function poll() {
      try {
        const resp = await fetch(
          `${API_ROOT}/runners/${runner}/sessions/${encodeURIComponent(sessionId)}/events`,
          { cache: "no-store" }
        );
        if (!resp.ok) throw new Error(`${resp.status}`);
        const data = await resp.json();
        if (!cancelled) {
          setEvents(data.events ?? []);
          setLastFetch(new Date().toLocaleTimeString("en-US", { hour12: false }));
          setFetchError(null);
        }
      } catch (e) {
        if (!cancelled) setFetchError(e instanceof Error ? e.message : "Fetch failed");
      }
    }

    poll();
    const interval = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [runner, sessionId, polling]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div style={{ padding: "12px 0" }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 0 10px",
        borderBottom: "1px solid var(--border)",
        marginBottom: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            display: "inline-block",
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: polling ? "var(--s-running)" : "var(--muted)",
            animation: polling ? "pulse 1.2s infinite" : "none",
          }} />
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            {polling ? "live" : "paused"} · {runner} · {events.length} events
          </span>
          {lastFetch && (
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
              updated {lastFetch}
            </span>
          )}
        </div>
        <button
          onClick={() => setPolling((p) => !p)}
          style={{
            background: "none",
            border: "1px solid var(--border)",
            padding: "2px 8px",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--muted)",
            cursor: "pointer",
          }}
        >
          {polling ? "Pause" : "Resume"}
        </button>
      </div>

      {fetchError && (
        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--s-failed)", marginBottom: 10 }}>
          {fetchError}
        </div>
      )}

      {events.length === 0 ? (
        <div className="empty-state">No events yet. Jules session may still be initialising.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {events.map((e, i) => (
            <div key={i} style={{
              display: "flex",
              alignItems: "baseline",
              gap: 10,
              padding: "4px 0",
              borderBottom: "1px solid var(--border)",
            }}>
              <span style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: eventColor(e.event_type),
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                flexShrink: 0,
                minWidth: 160,
              }}>
                {e.event_type.replace(/_/g, " ")}
              </span>
              <span style={{ fontSize: 12, color: "var(--fg)", lineHeight: 1.5 }}>
                {String(
                  e.normalized_payload.summary ??
                  e.normalized_payload.content ??
                  e.normalized_payload.message ??
                  e.normalized_payload.label ??
                  ""
                ).slice(0, 200) || "—"}
              </span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
