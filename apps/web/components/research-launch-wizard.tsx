"use client";

import { useState } from "react";
import { approveResearchLaunch, previewResearchLaunch } from "@/lib/api";
import { ResearchLaunchPayload, ResearchLaunchPreview } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

const WORKFLOWS = [
  ["feasibility_memo", "Feasibility memo"],
  ["source_inventory", "Source inventory"],
  ["literature_review", "Literature review"],
  ["data_pipeline", "Data pipeline"],
  ["econometric_model", "Econometric model"],
  ["policy_memo", "Policy memo"],
  ["technical_report", "Technical report"],
  ["presentation_deck", "Presentation deck"],
  ["data_workbook", "Data workbook/dashboard"],
];

const ROLES = ["planner", "research", "data", "coding", "artifact", "health"];

const DEFAULT_PAYLOAD: ResearchLaunchPayload = {
  researchQuestion: "",
  audience: "project stakeholders",
  deliverables: [],
  dataConstraints: "",
  publicOnly: true,
  citationStrictness: "strict",
  approvalBeforeWrites: true,
  useSubAgents: true,
  preferredAgentRoles: ["research", "data", "coding", "artifact"],
  workflowPresets: ["feasibility_memo", "source_inventory"],
  notes: "",
};

function toggle(list: string[], value: string) {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

export function ResearchLaunchWizard({ slug }: { slug: string }) {
  const [payload, setPayload] = useState<ResearchLaunchPayload>(DEFAULT_PAYLOAD);
  const [preview, setPreview] = useState<ResearchLaunchPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runPreview() {
    setBusy(true);
    setMessage(null);
    try {
      setPreview(await previewResearchLaunch(slug, payload));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await approveResearchLaunch(slug, payload);
      setPreview(result.preview);
      setMessage(`Created ${result.tasks.length} tasks and approval ${result.approvalId}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="launch-grid">
      <div className="launch-form">
        <label className="form-label">Research Question</label>
        <textarea
          className="form-textarea"
          value={payload.researchQuestion}
          onChange={(e) => setPayload({ ...payload, researchQuestion: e.target.value })}
          rows={5}
        />

        <label className="form-label">Audience</label>
        <input
          className="form-input"
          value={payload.audience}
          onChange={(e) => setPayload({ ...payload, audience: e.target.value })}
        />

        <label className="form-label">Workflow Presets</label>
        <div className="choice-grid">
          {WORKFLOWS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`choice-button${payload.workflowPresets.includes(key) ? " active" : ""}`}
              onClick={() => setPayload({ ...payload, workflowPresets: toggle(payload.workflowPresets, key) })}
            >
              {label}
            </button>
          ))}
        </div>

        <label className="form-label">Preferred Agent Roles</label>
        <div className="choice-grid compact">
          {ROLES.map((role) => (
            <button
              key={role}
              type="button"
              className={`choice-button${payload.preferredAgentRoles.includes(role) ? " active" : ""}`}
              onClick={() => setPayload({ ...payload, preferredAgentRoles: toggle(payload.preferredAgentRoles, role) })}
            >
              {role}
            </button>
          ))}
        </div>

        <label className="form-label">Data Constraints</label>
        <input
          className="form-input"
          value={payload.dataConstraints}
          onChange={(e) => setPayload({ ...payload, dataConstraints: e.target.value })}
        />

        <label className="form-label">Notes / Context</label>
        <textarea
          className="form-textarea"
          value={payload.notes}
          onChange={(e) => setPayload({ ...payload, notes: e.target.value })}
          rows={4}
        />

        <div className="toggle-row">
          <label><input type="checkbox" checked={payload.publicOnly} onChange={(e) => setPayload({ ...payload, publicOnly: e.target.checked })} /> Public data only</label>
          <label><input type="checkbox" checked={payload.approvalBeforeWrites} onChange={(e) => setPayload({ ...payload, approvalBeforeWrites: e.target.checked })} /> Approval before writes</label>
          <label><input type="checkbox" checked={payload.useSubAgents} onChange={(e) => setPayload({ ...payload, useSubAgents: e.target.checked })} /> Use sub-agents</label>
        </div>

        <label className="form-label">Citation Strictness</label>
        <select
          className="form-input"
          value={payload.citationStrictness}
          onChange={(e) => setPayload({ ...payload, citationStrictness: e.target.value })}
        >
          <option value="strict">Strict</option>
          <option value="standard">Standard</option>
          <option value="light">Light</option>
        </select>

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button className="command-button" disabled={busy} onClick={runPreview}>Preview Plan</button>
          <button className="command-button primary" disabled={busy || !preview} onClick={approve}>Create Tasks</button>
        </div>
        {message && <div className="launch-message">{message}</div>}
      </div>

      <div className="launch-preview">
        {!preview ? (
          <div className="empty-state">Preview will show proposed agents, skills, outputs, approvals, and risks.</div>
        ) : (
          <>
            <div className="preview-section">
              <div className="rail-label">Objective</div>
              <h2>{preview.objective}</h2>
              <div className="mono-muted">{preview.audience}</div>
            </div>
            <div className="preview-section">
              <div className="rail-label">Agent Work</div>
              {preview.agentWorkBreakdown.map((task, i) => (
                <div className="preview-task" key={i}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <strong>{task.title}</strong>
                    <StatusPill value={task.agentRole} />
                  </div>
                  <div className="mono-muted">{task.status} · {task.repoPaths.join(", ")}</div>
                </div>
              ))}
            </div>
            <div className="preview-section">
              <div className="rail-label">Skills</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {preview.skillsToUse.map((skill) => <StatusPill key={skill} value={skill} />)}
              </div>
            </div>
            <div className="preview-section">
              <div className="rail-label">Risks</div>
              <ul>{preview.knownRisks.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
