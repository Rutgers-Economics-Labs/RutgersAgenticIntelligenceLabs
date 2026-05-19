"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { createOrUpdateHypothesis, patchHypothesis } from "@/lib/api";
import { ClaimRecord, HypothesisRecord } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

const STATUSES: Array<HypothesisRecord["status"]> = [
  "draft",
  "supported",
  "weakened",
  "rejected",
  "archived",
];

export function HypothesesPanel({
  slug,
  hypotheses,
  claims,
  rankingById,
}: {
  slug: string;
  hypotheses: HypothesisRecord[];
  claims: ClaimRecord[];
  rankingById: Record<string, number>;
}) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [newStatement, setNewStatement] = useState("");
  const [newScope, setNewScope] = useState("");
  const [selectedClaims, setSelectedClaims] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);

  const claimOptions = useMemo(
    () =>
      claims.map((claim) => ({
        key: claim.claim_key,
        label: `${claim.claim_key} · ${claim.status}`,
      })),
    [claims],
  );

  const toggleClaim = (claimKey: string) => {
    const next = new Set(selectedClaims);
    if (next.has(claimKey)) next.delete(claimKey);
    else next.add(claimKey);
    setSelectedClaims(next);
  };

  const submitNew = async () => {
    const statement = newStatement.trim();
    if (!statement) {
      setMessage("Statement is required.");
      return;
    }
    setCreating(true);
    setMessage(null);
    try {
      const id = `hyp-${Math.random().toString(36).slice(2, 10)}`;
      await createOrUpdateHypothesis(slug, {
        id,
        statement,
        scope: newScope.trim() || undefined,
        claimKeys: Array.from(selectedClaims),
        status: "draft",
      });
      setNewStatement("");
      setNewScope("");
      setSelectedClaims(new Set());
      setMessage(`Created hypothesis ${id}.`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create hypothesis.");
    } finally {
      setCreating(false);
    }
  };

  const updateStatus = async (hypothesis: HypothesisRecord, status: HypothesisRecord["status"]) => {
    setBusyId(hypothesis.id);
    setMessage(null);
    try {
      await patchHypothesis(slug, hypothesis.id, { status });
      setMessage(`Updated ${hypothesis.id} to ${status}.`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update hypothesis.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="agent-run-card" style={{ display: "grid", gap: 10 }}>
        <strong>Create hypothesis</strong>
        <input
          value={newStatement}
          onChange={(event) => setNewStatement(event.target.value)}
          placeholder="Hypothesis statement"
        />
        <input
          value={newScope}
          onChange={(event) => setNewScope(event.target.value)}
          placeholder="Scope (optional)"
        />
        <div className="mono-muted">Link to claims</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {claimOptions.length ? (
            claimOptions.slice(0, 10).map((option) => (
              <label key={option.key} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={selectedClaims.has(option.key)}
                  onChange={() => toggleClaim(option.key)}
                />
                <span className="mono-muted">{option.label}</span>
              </label>
            ))
          ) : (
            <span className="mono-muted">No claims yet.</span>
          )}
        </div>
        <div>
          <button className="command-button primary" disabled={creating} onClick={submitNew}>
            {creating ? "Creating..." : "Create hypothesis"}
          </button>
        </div>
      </div>

      {message ? <div className="empty-state">{message}</div> : null}

      {hypotheses.length ? (
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Statement</th>
              <th>Status</th>
              <th>Score</th>
              <th>Claims</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {hypotheses.map((hypothesis) => (
              <tr key={hypothesis.id}>
                <td>
                  <strong>{hypothesis.id}</strong>
                  <div className="mono-muted">{hypothesis.scope || "no-scope"}</div>
                </td>
                <td>{hypothesis.statement}</td>
                <td><StatusPill value={hypothesis.status} /></td>
                <td className="mono-muted">
                  {typeof rankingById[hypothesis.id] === "number"
                    ? rankingById[hypothesis.id].toFixed(2)
                    : hypothesis.score?.toFixed(2) ?? "—"}
                </td>
                <td className="mono-muted">{hypothesis.claim_keys.join(", ") || "—"}</td>
                <td>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {STATUSES.map((status) => (
                      <button
                        key={status}
                        className="command-button"
                        disabled={busyId === hypothesis.id || hypothesis.status === status}
                        onClick={() => updateStatus(hypothesis, status)}
                      >
                        {status}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="empty-state">No hypotheses recorded yet.</div>
      )}
    </div>
  );
}

