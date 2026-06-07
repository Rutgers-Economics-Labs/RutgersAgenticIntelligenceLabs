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

const KICKOFF_RECIPES = [
  {
    label: "Validation wave",
    question: "What is the strongest next validation wave for this project, and what tasks should we launch first?",
    audience: "project stakeholders",
    workflowPresets: ["feasibility_memo", "source_inventory", "data_pipeline"],
    preferredAgentRoles: ["research", "data", "coding"],
    notes: "Focus on verification-ready sources, clear acceptance criteria, and repo-backed outputs.",
  },
  {
    label: "Research memo",
    question: "Produce a defensible memo that answers the current project question with clear evidence boundaries and follow-up tasks.",
    audience: "policy and research stakeholders",
    workflowPresets: ["literature_review", "policy_memo", "technical_report"],
    preferredAgentRoles: ["research", "coding", "artifact"],
    notes: "Keep the launch scoped to memo-quality evidence and publication-safe claims.",
  },
  {
    label: "Data buildout",
    question: "What data engineering and profiling work should start next to make this project analysis-ready?",
    audience: "data and modeling team",
    workflowPresets: ["source_inventory", "data_pipeline", "data_workbook"],
    preferredAgentRoles: ["data", "coding", "health"],
    notes: "Prioritize ingestion, quality profiling, and reproducible intermediate outputs.",
  },
];

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

function applyRecipe(recipe: (typeof KICKOFF_RECIPES)[number]): ResearchLaunchPayload {
  return {
    ...DEFAULT_PAYLOAD,
    researchQuestion: recipe.question,
    audience: recipe.audience,
    workflowPresets: recipe.workflowPresets,
    preferredAgentRoles: recipe.preferredAgentRoles,
    notes: recipe.notes,
  };
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
        <div className="preview-section" style={{ paddingBottom: 16 }}>
          <div className="rail-label">Launch Purpose</div>
          <h2 style={{ marginTop: 8 }}>Kick off a new work package before it hits the planner board.</h2>
          <div className="mono-muted" style={{ lineHeight: 1.7 }}>
            Use Launch when you have a fresh question or a new wave of work. It generates a preview of tasks, roles, approvals, risks, and expected outputs before anything is created.
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            {KICKOFF_RECIPES.map((recipe) => (
              <button
                key={recipe.label}
                type="button"
                className="choice-button"
                onClick={() => setPayload(applyRecipe(recipe))}
              >
                {recipe.label}
              </button>
            ))}
          </div>
        </div>

        <label className="form-label">What new work should we kick off?</label>
        <textarea
          className="form-textarea"
          value={payload.researchQuestion}
          onChange={(e) => setPayload({ ...payload, researchQuestion: e.target.value })}
          rows={5}
          placeholder="Describe the new research wave, memo, model, or data buildout you want the system to plan."
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
          placeholder="Optional: public-only, no paid APIs, local files only, US data only..."
        />

        <label className="form-label">Notes / Context</label>
        <textarea
          className="form-textarea"
          value={payload.notes}
          onChange={(e) => setPayload({ ...payload, notes: e.target.value })}
          rows={4}
          placeholder="Optional: known sources, deadlines, acceptance standards, or constraints the planner should respect."
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

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 10, marginTop: 14 }}>
          <div className="overview-meta-card">
            <div className="rail-label">Presets</div>
            <div className="overview-meta-value" style={{ fontSize: 18 }}>{payload.workflowPresets.length}</div>
          </div>
          <div className="overview-meta-card">
            <div className="rail-label">Roles</div>
            <div className="overview-meta-value" style={{ fontSize: 18 }}>{payload.preferredAgentRoles.length}</div>
          </div>
          <div className="overview-meta-card">
            <div className="rail-label">Safety</div>
            <div className="overview-meta-value" style={{ fontSize: 18 }}>
              {payload.approvalBeforeWrites ? "Gated" : "Open"}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button className="command-button" disabled={busy || !payload.researchQuestion.trim()} onClick={runPreview}>
            {busy ? "Working..." : "Generate Preview"}
          </button>
          <button className="command-button primary" disabled={busy || !preview} onClick={approve}>Create Kickoff Tasks</button>
        </div>
        {message && <div className="launch-message">{message}</div>}
      </div>

      <div className="launch-preview">
        {!preview ? (
          <div style={{ display: "grid", gap: 18 }}>
            <div className="preview-section">
              <div className="rail-label">How Launch Works</div>
              <h2 style={{ marginTop: 8 }}>Preview first, then create tasks.</h2>
              <div className="mono-muted" style={{ lineHeight: 1.7 }}>
                The preview side will show the proposed objective, task breakdown, skills, outputs, approvals, missing inputs, and risks before anything is written to the planner board.
              </div>
            </div>

            <div className="preview-section">
              <div className="rail-label">Current Selection</div>
              <div className="overview-mini-list" style={{ marginTop: 10 }}>
                <div className="overview-mini-item">
                  <div className="rail-label">Question</div>
                  <div style={{ fontWeight: 700, color: "var(--fg)" }}>
                    {payload.researchQuestion.trim() || "Add the new work request on the left."}
                  </div>
                </div>
                <div className="overview-mini-item">
                  <div className="rail-label">Workflows</div>
                  <div className="mono-muted">
                    {payload.workflowPresets.length ? payload.workflowPresets.join(" · ").replaceAll("_", " ") : "No presets selected"}
                  </div>
                </div>
                <div className="overview-mini-item">
                  <div className="rail-label">Roles</div>
                  <div className="mono-muted">
                    {payload.preferredAgentRoles.length ? payload.preferredAgentRoles.join(" · ") : "No roles selected"}
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="preview-section">
              <div className="rail-label">Objective</div>
              <h2>{preview.objective}</h2>
              <div className="mono-muted">{preview.audience}</div>
            </div>
            <div className="preview-section">
              <div className="rail-label">Launch Summary</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 10, marginTop: 10 }}>
                <div className="overview-meta-card">
                  <div className="rail-label">Tasks</div>
                  <div className="overview-meta-value" style={{ fontSize: 18 }}>{preview.agentWorkBreakdown.length}</div>
                </div>
                <div className="overview-meta-card">
                  <div className="rail-label">Outputs</div>
                  <div className="overview-meta-value" style={{ fontSize: 18 }}>{preview.expectedRepoOutputs.length}</div>
                </div>
                <div className="overview-meta-card">
                  <div className="rail-label">Approvals</div>
                  <div className="overview-meta-value" style={{ fontSize: 18 }}>{preview.requiredApprovals.length}</div>
                </div>
              </div>
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
              <div className="rail-label">Expected Outputs</div>
              <ul>
                {preview.expectedRepoOutputs.map((output) => <li key={output}>{output}</li>)}
              </ul>
            </div>
            {preview.requiredApprovals.length ? (
              <div className="preview-section">
                <div className="rail-label">Required Approvals</div>
                <ul>
                  {preview.requiredApprovals.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
            {preview.missingInputs.length ? (
              <div className="preview-section">
                <div className="rail-label">Missing Inputs</div>
                <ul>
                  {preview.missingInputs.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
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
