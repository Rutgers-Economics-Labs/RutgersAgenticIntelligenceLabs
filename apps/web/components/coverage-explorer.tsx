"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { CommandCenter } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

type OntologyClass = { name: string; count: number };

const CLASSIFICATION_LABELS: Record<string, string> = {
  answerable_now: "Answerable now",
  answerable_after_requery: "Answerable after requery",
  requires_expansion: "Needs ontology expansion",
  blocked_by_data: "Blocked by data",
  unknown: "Unclassified",
};

const CLASSIFICATION_TONE: Record<string, "ok" | "warn" | "info" | "block"> = {
  answerable_now: "ok",
  answerable_after_requery: "info",
  requires_expansion: "warn",
  blocked_by_data: "block",
  unknown: "info",
};

/**
 * Ontology coverage explorer: spec view from
 * docs/future-spec-ui-and-control-plane.md#ontology-coverage-explorer.
 *
 * Joins three signals into one place so the operator can reason about what
 * questions can be answered *right now* vs which would require ontology
 * expansion:
 *   - Class counts (the materialized coverage)
 *   - Follow-up question classifications (answerable / requery / expand / blocked)
 *   - Sparse-class detection (count == 0 → known partial coverage)
 *
 * The expansion proposal column is the spec's "what would unlock the next best
 * question?" surface — each non-answerable-now question links to the planner
 * task that would close the gap when one already exists.
 */
export function CoverageExplorer({
  slug,
  center,
  classes,
}: {
  slug: string;
  center: CommandCenter;
  classes: OntologyClass[];
}) {
  const followUps = center.ontologyFollowUps;
  const counts = followUps?.classificationCounts ?? {};
  const questions = followUps?.questions ?? [];
  const totalQuestions = questions.length;
  const populated = classes.filter((c) => c.count > 0);
  const empty = classes.filter((c) => c.count === 0);

  return (
    <div style={{ display: "grid", gap: 24 }}>
      <section>
        <SectionHeader
          title="Coverage map"
          sub={`${populated.length} populated · ${empty.length} empty · ${classes.length} total classes`}
        />
        {classes.length === 0 ? (
          <Empty>No class data — run hydration to populate the ontology.</Empty>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
              gap: 8,
              padding: "10px 14px",
            }}
          >
            {classes
              .slice()
              .sort((a, b) => b.count - a.count)
              .map((c) => {
                const empty = c.count === 0;
                return (
                  <div
                    key={c.name}
                    style={{
                      border: `1px solid ${empty ? "var(--border)" : "var(--border-strong)"}`,
                      padding: "8px 10px",
                      borderRadius: 4,
                      background: empty ? "var(--panel)" : "var(--panel-alt)",
                      opacity: empty ? 0.6 : 1,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: "var(--fg)", fontSize: 13, wordBreak: "break-word" }}>
                      {c.name}
                    </div>
                    <div
                      style={{
                        marginTop: 4,
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 11,
                        color: empty ? "var(--muted)" : "var(--fg)",
                      }}
                    >
                      {c.count} instance{c.count === 1 ? "" : "s"}
                      {empty ? " · empty" : ""}
                    </div>
                  </div>
                );
              })}
          </div>
        )}
      </section>

      <section>
        <SectionHeader
          title="Question coverage"
          sub={
            totalQuestions
              ? `${totalQuestions} follow-up questions classified`
              : "No follow-up questions detected"
          }
        />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 8,
            padding: "10px 14px",
          }}
        >
          {Object.entries(CLASSIFICATION_LABELS).map(([key, label]) => {
            const value = counts[key] ?? 0;
            return (
              <ClassificationTile
                key={key}
                label={label}
                value={value}
                tone={CLASSIFICATION_TONE[key]}
              />
            );
          })}
        </div>

        {questions.length === 0 ? (
          <Empty>
            Generate follow-up questions by running an artifact synthesis pass or by adding
            <code> research_plan/ontology_answerable_follow_up_questions.md</code>.
          </Empty>
        ) : (
          <div style={{ padding: "10px 14px", display: "grid", gap: 6 }}>
            {questions.slice(0, 20).map((q) => {
              const classification = String(q.classification || "unknown").toLowerCase();
              const tone = CLASSIFICATION_TONE[classification] ?? "info";
              return (
                <div
                  key={q.title}
                  style={{
                    border: "1px solid var(--border)",
                    borderLeft: `3px solid ${toneColor(tone)}`,
                    padding: "8px 10px",
                    borderRadius: 4,
                    background: "var(--panel)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 8,
                      alignItems: "flex-start",
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ fontWeight: 600, color: "var(--fg)", fontSize: 13 }}>{q.title}</div>
                    <StatusPill
                      value={CLASSIFICATION_LABELS[classification] ?? classification}
                    />
                  </div>
                  {q.notes && q.notes.length > 0 ? (
                    <ul
                      style={{
                        margin: "6px 0 0",
                        padding: "0 0 0 18px",
                        color: "var(--muted)",
                        fontSize: 12,
                      }}
                    >
                      {q.notes.slice(0, 3).map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  ) : null}
                  {q.expectedTaskTitle ? (
                    <div
                      style={{
                        marginTop: 6,
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 10,
                        color: "var(--muted)",
                      }}
                    >
                      {q.taskPresent ? (
                        <Link href={`/projects/${slug}/planner`} style={{ color: "var(--muted)" }}>
                          ↪ planner task ({q.taskStatus ?? "pending"}): {q.expectedTaskTitle}
                        </Link>
                      ) : (
                        <span>Would create planner task: {q.expectedTaskTitle}</span>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function SectionHeader({ title, sub }: { title: string; sub: string }) {
  return (
    <div
      style={{
        padding: "10px 14px 8px",
        borderBottom: "1px solid var(--border)",
        background: "var(--panel)",
      }}
    >
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700, color: "var(--fg)" }}>
        {title}
      </div>
      <div className="rail-label" style={{ marginTop: 2 }}>{sub}</div>
    </div>
  );
}

function ClassificationTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "ok" | "warn" | "info" | "block";
}) {
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderTop: `3px solid ${toneColor(tone)}`,
        padding: "8px 10px",
        borderRadius: 4,
        background: "var(--panel-alt)",
      }}
    >
      <div className="rail-label">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: value ? "var(--fg)" : "var(--muted)", marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty-state" style={{ padding: "12px 14px", color: "var(--muted)", fontSize: 12 }}>
      {children}
    </div>
  );
}

function toneColor(tone: "ok" | "warn" | "info" | "block"): string {
  switch (tone) {
    case "ok":    return "var(--ok, #10b981)";
    case "warn":  return "var(--warning, #f59e0b)";
    case "block": return "var(--error, #ef4444)";
    case "info":  return "var(--accent, #3b82f6)";
  }
}
