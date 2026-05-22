"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { configureProjectGoal } from "@/lib/api";
import type { GoalBundle } from "@/lib/types";

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function GoalModeComposer({
  slug,
  existingGoal,
  suggestedObjective,
}: {
  slug: string;
  existingGoal?: GoalBundle | null;
  suggestedObjective?: string;
}) {
  const router = useRouter();
  const [objective, setObjective] = useState(existingGoal?.contract?.objective ?? suggestedObjective ?? "");
  const [successCriteria, setSuccessCriteria] = useState(
    existingGoal?.contract?.successCriteria?.join("\n") ??
      "hydrated ontology exists\nfinal artifacts have provenance-backed claims\ncloseout audit passes",
  );
  const [requiredEvidence, setRequiredEvidence] = useState(
    existingGoal?.contract?.requiredEvidence?.join("\n") ??
      "source registry entries\nhydration or dataset artifact path\nverification or closeout evidence",
  );
  const [forbiddenShortcuts, setForbiddenShortcuts] = useState(
    existingGoal?.contract?.forbiddenShortcuts?.join("\n") ??
      "do not use placeholder sources as trusted evidence\ndo not mark complete from activity alone",
  );
  const [escalationPolicy, setEscalationPolicy] = useState(
    existingGoal?.contract?.escalationPolicy?.join("\n") ??
      "pause only for scope decisions\npause only for access or credential decisions\npause only for trust or acceptance decisions",
  );
  const [retries, setRetries] = useState(String(existingGoal?.contract?.allowedSpend?.retries ?? 3));
  const [timeMinutes, setTimeMinutes] = useState(String(existingGoal?.contract?.allowedSpend?.timeMinutes ?? 180));
  const [launchAutopilot, setLaunchAutopilot] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function handleSave() {
    setError(null);
    setMessage(null);
    if (!objective.trim()) {
      setError("Objective is required.");
      return;
    }
    const criteria = splitLines(successCriteria);
    if (!criteria.length) {
      setError("At least one success criterion is required.");
      return;
    }
    startTransition(async () => {
      try {
        const response = await configureProjectGoal(slug, {
          objective: objective.trim(),
          successCriteria: criteria,
          requiredEvidence: splitLines(requiredEvidence),
          forbiddenShortcuts: splitLines(forbiddenShortcuts),
          escalationPolicy: splitLines(escalationPolicy),
          allowedSpend: {
            retries: Number(retries) || 0,
            timeMinutes: Number(timeMinutes) || null,
          },
          launchAutopilot,
        });
        const preflight = response.preflight as { passed?: boolean; currentBlocker?: string | null } | undefined;
        if (preflight?.passed) {
          setMessage(launchAutopilot ? "Goal saved. Autopilot launch queued." : "Goal saved.");
        } else {
          setMessage(`Goal saved, but preflight is still blocked${preflight?.currentBlocker ? `: ${preflight.currentBlocker}` : "."}`);
        }
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save goal.");
      }
    });
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Field
        label="Objective"
        value={objective}
        onChange={setObjective}
        placeholder="Explain how weather and fuel shocks affect PJM/NYISO/ISO-NE prices"
        rows={3}
      />
      <Field
        label="Success Criteria"
        value={successCriteria}
        onChange={setSuccessCriteria}
        placeholder="One line per criterion"
        rows={4}
      />
      <Field
        label="Required Evidence"
        value={requiredEvidence}
        onChange={setRequiredEvidence}
        placeholder="One line per evidence requirement"
        rows={3}
      />
      <Field
        label="Forbidden Shortcuts"
        value={forbiddenShortcuts}
        onChange={setForbiddenShortcuts}
        placeholder="One line per shortcut to forbid"
        rows={3}
      />
      <Field
        label="Escalation Policy"
        value={escalationPolicy}
        onChange={setEscalationPolicy}
        placeholder="One line per escalation rule"
        rows={3}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
        <SmallField label="Retry Budget" value={retries} onChange={setRetries} />
        <SmallField label="Time Budget (min)" value={timeMinutes} onChange={setTimeMinutes} />
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--fg)", fontSize: 13 }}>
        <input
          type="checkbox"
          checked={launchAutopilot}
          onChange={(event) => setLaunchAutopilot(event.target.checked)}
        />
        Queue autopilot launch if preflight passes
      </label>

      {message ? <div className="mono-muted">{message}</div> : null}
      {error ? <div style={{ color: "var(--error)", fontSize: 12 }}>{error}</div> : null}

      <button
        onClick={handleSave}
        disabled={isPending}
        style={{
          border: "1px solid var(--border)",
          background: "var(--fg)",
          color: "var(--bg)",
          padding: "10px 12px",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          textTransform: "uppercase",
          cursor: isPending ? "not-allowed" : "pointer",
        }}
      >
        {isPending ? "Saving..." : existingGoal ? "Update Goal Contract" : "Create Goal Contract"}
      </button>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  rows,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  rows: number;
}) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span className="rail-label">{label}</span>
      <textarea
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        style={{
          width: "100%",
          border: "1px solid var(--border)",
          background: "var(--bg)",
          color: "var(--fg)",
          padding: "10px 12px",
          resize: "vertical",
          fontSize: 13,
        }}
      />
    </label>
  );
}

function SmallField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span className="rail-label">{label}</span>
      <input
        type="number"
        min={0}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={{
          width: "100%",
          border: "1px solid var(--border)",
          background: "var(--bg)",
          color: "var(--fg)",
          padding: "10px 12px",
          fontSize: 13,
        }}
      />
    </label>
  );
}
