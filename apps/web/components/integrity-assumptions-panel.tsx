"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  applyBatchIntegrityRerunPlan,
  applyIntegrityRerunPlan,
  previewBatchIntegrityRerunPlan,
  previewIntegrityRerunPlan,
  updateIntegrityAssumption,
} from "@/lib/api";
import { AssumptionRecord, ArtifactLineageRecord, IntegrityRerunPlan } from "@/lib/types";
import { buildAffectedArtifactMap } from "@/lib/integrity";
import { StatusPill } from "@/components/status-pill";

export function IntegrityAssumptionsPanel({
  slug,
  assumptions,
  artifactLineage,
}: {
  slug: string;
  assumptions: AssumptionRecord[];
  artifactLineage: ArtifactLineageRecord[];
}) {
  const router = useRouter();
  const affectedMap = useMemo(() => buildAffectedArtifactMap(assumptions, artifactLineage), [assumptions, artifactLineage]);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [draftNotes, setDraftNotes] = useState("");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [plan, setPlan] = useState<IntegrityRerunPlan | null>(null);

  const toggleSelect = (key: string) => {
    const next = new Set(selectedKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setSelectedKeys(next);
  };

  async function previewPlan(assumptionKey?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const keys = assumptionKey ? [assumptionKey] : Array.from(selectedKeys);
      if (!keys.length) return;
      const nextPlan = keys.length === 1 
        ? await previewIntegrityRerunPlan(slug, keys[0])
        : await previewBatchIntegrityRerunPlan(slug, keys);
      setPlan(nextPlan);
      setMessage(`Previewing rerun plan for ${keys.length} assumption(s).`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not build rerun plan.");
    } finally {
      setBusy(false);
    }
  }

  async function saveAssumption(row: AssumptionRecord) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await updateIntegrityAssumption(slug, row.assumption_key, {
        value: draftValue,
        notes: draftNotes,
      });
      setPlan(result.rerunPlan);
      setEditingKey(null);
      setMessage(`Marked ${row.assumption_key} changed and refreshed its rerun plan.`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update assumption.");
    } finally {
      setBusy(false);
    }
  }

  async function applyPlan() {
    if (!plan) return;
    setBusy(true);
    setMessage(null);
    try {
      const keys = plan.assumptions 
        ? plan.assumptions.map(a => a.assumption_key)
        : plan.assumption ? [plan.assumption.assumption_key] : [];
      
      const result = keys.length > 1
        ? await applyBatchIntegrityRerunPlan(slug, keys)
        : await applyIntegrityRerunPlan(slug, keys[0]);
        
      setPlan(result.rerunPlan);
      setMessage(`Created ${result.tasks.length} rerun tasks.`);
      setSelectedKeys(new Set());
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create rerun tasks.");
    } finally {
      setBusy(false);
    }
  }

  if (!assumptions.length) {
    return <div className="empty-state">No assumptions recorded yet.</div>;
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button 
          className="command-button" 
          disabled={busy || selectedKeys.size === 0} 
          onClick={() => previewPlan()}
        >
          Preview Rerun for {selectedKeys.size} Selected
        </button>
        {selectedKeys.size > 0 && (
          <button className="command-button ghost" onClick={() => setSelectedKeys(new Set())}>
            Clear Selection
          </button>
        )}
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th style={{ width: 40 }}></th>
            <th>Key</th>
            <th>Value</th>
            <th>Status</th>
            <th>Affected Outputs</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {assumptions.map((row) => {
            const affected = affectedMap[row.assumption_key] ?? row.affected_paths;
            const editing = editingKey === row.assumption_key;
            const selected = selectedKeys.has(row.assumption_key);
            return (
              <tr key={row.assumption_key} className={selected ? "selected" : ""}>
                <td>
                  <input 
                    type="checkbox" 
                    checked={selected} 
                    onChange={() => toggleSelect(row.assumption_key)} 
                  />
                </td>
                <td>
                  <strong>{row.title}</strong>
                  <div className="mono-muted">{row.assumption_key}</div>
                </td>
                <td style={{ minWidth: 260 }}>
                  {editing ? (
                    <div style={{ display: "grid", gap: 8 }}>
                      <textarea value={draftValue} onChange={(e) => setDraftValue(e.target.value)} rows={3} />
                      <textarea value={draftNotes} onChange={(e) => setDraftNotes(e.target.value)} rows={2} placeholder="Why did this change?" />
                    </div>
                  ) : (
                    row.value
                  )}
                </td>
                <td><StatusPill value={row.status} /></td>
                <td className="mono-muted">{affected.join(", ") || "—"}</td>
                <td>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {editing ? (
                      <>
                        <button className="command-button primary" type="button" disabled={busy} onClick={() => saveAssumption(row)}>
                          {busy ? "Saving" : "Save + Preview Rerun"}
                        </button>
                        <button className="command-button" type="button" disabled={busy} onClick={() => setEditingKey(null)}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          className="command-button"
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            setEditingKey(row.assumption_key);
                            setDraftValue(row.value);
                            setDraftNotes(row.notes ?? "");
                          }}
                        >
                          Edit
                        </button>
                        <button className="command-button" type="button" disabled={busy} onClick={() => previewPlan(row.assumption_key)}>
                          Preview Rerun
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {message && <div className="empty-state">{message}</div>}

      {plan && (
        <div className="agent-run-card" style={{ display: "grid", gap: 12 }}>
          <div>
            <strong>Rerun Plan</strong>
            <div className="mono-muted">
              {plan.assumptions 
                ? `${plan.assumptions.length} assumptions: ${plan.assumptions.map(a => a.assumption_key).join(", ")}`
                : plan.assumption?.assumption_key}
            </div>
          </div>
          <div className="mono-muted">
            Affected outputs: {plan.affectedPaths.join(", ") || "—"}
          </div>
          <div className="mono-muted">
            Stale now: {plan.stalePaths.join(", ") || "—"}
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {plan.proposedTasks.map((task) => (
              <div key={task.title} style={{ border: "1px solid var(--border)", borderRadius: 12, padding: 12 }}>
                <div style={{ fontWeight: 600 }}>{task.title}</div>
                <div className="mono-muted">{task.agentRole} · {task.repoPaths.join(", ")}</div>
                <div style={{ marginTop: 6 }}>{task.description}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="command-button primary" type="button" disabled={busy} onClick={() => applyPlan()}>
              {busy ? "Creating" : "Create Rerun Tasks"}
            </button>
            <button className="command-button" type="button" disabled={busy} onClick={() => setPlan(null)}>
              Clear Preview
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
