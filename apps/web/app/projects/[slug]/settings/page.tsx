"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ProjectShell } from "@/components/project-shell";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

// ── Helpers ────────────────────────────────────────────────────────────

async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_ROOT}${path}`, { cache: "no-store", ...init });
  if (!resp.ok) throw new Error(`API ${path} failed: ${resp.status}`);
  return resp.json() as Promise<T>;
}
async function postJson<T = unknown>(path: string, body: unknown): Promise<T> {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
async function deleteApi(path: string) {
  const resp = await fetch(`${API_ROOT}${path}`, { method: "DELETE", cache: "no-store" });
  if (!resp.ok) throw new Error(`DELETE ${path} failed: ${resp.status}`);
  return resp.json();
}

// ── Styling tokens ─────────────────────────────────────────────────────

const LABEL: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace", fontSize: 10,
  letterSpacing: "0.12em", textTransform: "uppercase",
  color: "var(--muted)", marginBottom: 6,
};
const INPUT: React.CSSProperties = {
  width: "100%", boxSizing: "border-box",
  background: "var(--bg)", border: "1px solid var(--border)",
  color: "var(--fg)", fontFamily: "JetBrains Mono, monospace",
  fontSize: 12, padding: "7px 10px", outline: "none",
};
const BTN: React.CSSProperties = {
  padding: "6px 14px", border: "1px solid var(--border)",
  background: "var(--panel-alt)", fontFamily: "JetBrains Mono, monospace",
  fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase",
  color: "var(--fg)", cursor: "pointer",
};
const BTN_PRIMARY: React.CSSProperties = {
  ...BTN, background: "var(--fg)", color: "var(--bg)", border: "1px solid var(--border-strong)",
};
const BTN_DANGER: React.CSSProperties = {
  ...BTN, color: "var(--s-failed)", borderColor: "var(--s-failed)",
};
const SECTION: React.CSSProperties = {
  borderBottom: "1px solid var(--border)", padding: "20px 24px",
};
const FIELD: React.CSSProperties = { marginBottom: 14 };

// ── Section: General Metadata ──────────────────────────────────────────

function GeneralSection({ slug }: { slug: string }) {
  const [project, setProject] = useState<any>(null);
  const [form, setForm] = useState({ name: "", description: "", gitRepoUrl: "", defaultBranch: "main", agentModel: "" });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api(`/projects/${slug}/command-center`).then((data: any) => {
      const p = data.project;
      setProject(p);
      setForm({
        name: p.name ?? "",
        description: p.description ?? "",
        gitRepoUrl: p.gitRepoUrl ?? "",
        defaultBranch: p.defaultBranch ?? "main",
        agentModel: p.agentModel ?? "",
      });
    }).catch(() => {});
  }, [slug]);

  async function save() {
    setSaving(true);
    try {
      await postJson(`/projects/${slug}/sync-metadata`, form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {}
    setSaving(false);
  }

  if (!project) return <div style={SECTION}><span style={LABEL}>Loading…</span></div>;

  return (
    <div style={SECTION}>
      <div style={{ ...LABEL, marginBottom: 14, fontSize: 11 }}>General</div>

      <div style={FIELD}>
        <div style={LABEL}>Project name</div>
        <input style={INPUT} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </div>
      <div style={FIELD}>
        <div style={LABEL}>Description</div>
        <textarea style={{ ...INPUT, resize: "vertical", lineHeight: 1.5 }} rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        <div>
          <div style={LABEL}>Git repo URL</div>
          <input style={INPUT} value={form.gitRepoUrl} onChange={(e) => setForm({ ...form, gitRepoUrl: e.target.value })} placeholder="https://github.com/org/repo" />
        </div>
        <div>
          <div style={LABEL}>Default branch</div>
          <input style={INPUT} value={form.defaultBranch} onChange={(e) => setForm({ ...form, defaultBranch: e.target.value })} />
        </div>
      </div>
      <div style={FIELD}>
        <div style={LABEL}>Agent model override</div>
        <input style={INPUT} value={form.agentModel} onChange={(e) => setForm({ ...form, agentModel: e.target.value })} placeholder="e.g. claude-opus-4-6, gemini/gemini-2.5-pro" />
        <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>
          Leave blank to use the server default. Supports LiteLLM model strings.
        </div>
      </div>

      <div style={{ display: "flex", gap: 14, marginBottom: 10 }}>
        <div>
          <div style={LABEL}>Local repo path</div>
          <div style={{ fontSize: 12, fontFamily: "JetBrains Mono, monospace", color: "var(--fg)", opacity: 0.7 }}>
            {project.localRepoPath ?? "—"}
          </div>
        </div>
        <div>
          <div style={LABEL}>Slug</div>
          <div style={{ fontSize: 12, fontFamily: "JetBrains Mono, monospace", color: "var(--fg)", opacity: 0.7 }}>
            {slug}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 16 }}>
        <button style={BTN_PRIMARY} onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </button>
        {saved && <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--s-done)" }}>✓ Saved</span>}
      </div>
    </div>
  );
}

// ── Section: Secrets ───────────────────────────────────────────────────

function SecretsSection({ slug }: { slug: string }) {
  const [secrets, setSecrets] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      const data: any = await api(`/projects/${slug}/settings/secrets`);
      setSecrets(data.secrets ?? []);
      setPolicies(data.policies ?? []);
    } catch {}
    setLoading(false);
  }, [slug]);

  useEffect(() => { load(); }, [load]);

  async function addSecret() {
    if (!newKey.trim() || !newVal.trim()) return;
    setAdding(true);
    try {
      await postJson(`/projects/${slug}/settings/secrets`, { keyName: newKey.trim(), plaintextValue: newVal.trim() });
      setNewKey(""); setNewVal("");
      load();
    } catch {}
    setAdding(false);
  }

  async function removeSecret(keyName: string) {
    try {
      await deleteApi(`/projects/${slug}/settings/secrets/${encodeURIComponent(keyName)}`);
      load();
    } catch {}
  }

  return (
    <div style={SECTION}>
      <div style={{ ...LABEL, marginBottom: 14, fontSize: 11 }}>Secrets</div>

      {loading ? (
        <div style={{ ...LABEL }}>Loading…</div>
      ) : (
        <>
          {/* Existing secrets */}
          {secrets.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", marginBottom: 14 }}>
              No secrets configured.
            </div>
          ) : (
            <div style={{ marginBottom: 14 }}>
              {secrets.map((s: any) => (
                <div key={s.keyName} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
                  padding: "8px 10px", borderBottom: "1px solid var(--border)", background: "var(--bg)",
                }}>
                  <div style={{ display: "flex", gap: 12, alignItems: "center", minWidth: 0 }}>
                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, fontWeight: 600, color: "var(--fg)" }}>
                      {s.keyName}
                    </span>
                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>
                      {s.maskedValue ?? "••••••••"}
                    </span>
                  </div>
                  <button style={{ ...BTN_DANGER, padding: "2px 8px", fontSize: 9 }} onClick={() => removeSecret(s.keyName)}>
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Add new */}
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <div style={LABEL}>Key name</div>
              <input style={INPUT} value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="e.g. FRED_API_KEY" />
            </div>
            <div style={{ flex: 2 }}>
              <div style={LABEL}>Value</div>
              <input style={INPUT} type="password" value={newVal} onChange={(e) => setNewVal(e.target.value)} placeholder="Secret value" />
            </div>
            <button style={{ ...BTN_PRIMARY, flexShrink: 0 }} disabled={adding || !newKey.trim() || !newVal.trim()} onClick={addSecret}>
              {adding ? "…" : "Add"}
            </button>
          </div>

          {/* Agent secret policies */}
          {policies.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <div style={LABEL}>Agent secret policies</div>
              {policies.map((p: any) => (
                <div key={p.agentRole} style={{
                  padding: "6px 10px", borderBottom: "1px solid var(--border)",
                  display: "flex", gap: 10, alignItems: "center",
                }}>
                  <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 600, color: "var(--fg)" }}>
                    {p.agentRole}
                  </span>
                  <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                    → {(p.allowedSecretNames ?? []).join(", ") || "none"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Section: Git & GitHub ──────────────────────────────────────────────

function GitSection({ slug }: { slug: string }) {
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    api(`/projects/${slug}/command-center`).then((data: any) => setInfo(data)).catch(() => {});
  }, [slug]);

  if (!info) return <div style={SECTION}><span style={LABEL}>Loading…</span></div>;

  const p = info.project;
  const repo = info.repoHealth;

  return (
    <div style={SECTION}>
      <div style={{ ...LABEL, marginBottom: 14, fontSize: 11 }}>Git & GitHub</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 14 }}>
        {[
          { label: "GitHub repo", value: p.gitRepoUrl ? p.gitRepoUrl.replace("https://github.com/", "") : "—" },
          { label: "GitHub sync", value: p.githubSyncMode ?? "auto" },
          { label: "Default branch", value: p.defaultBranch ?? "main" },
        ].map(({ label, value }) => (
          <div key={label}>
            <div style={LABEL}>{label}</div>
            <div style={{ fontSize: 12, fontFamily: "JetBrains Mono, monospace", color: "var(--fg)" }}>{value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
        {[
          { label: "Local repo", value: repo?.hasLocalRepo ? "✓ present" : "✗ missing", ok: repo?.hasLocalRepo },
          { label: "rail.yaml", value: repo?.hasRailYaml ? "✓ present" : "✗ missing", ok: repo?.hasRailYaml },
          { label: "Research plan", value: repo?.hasResearchPlan ? "✓ present" : "✗ missing", ok: repo?.hasResearchPlan },
        ].map(({ label, value, ok }) => (
          <div key={label}>
            <div style={LABEL}>{label}</div>
            <div style={{ fontSize: 12, fontFamily: "JetBrains Mono, monospace", color: ok ? "var(--s-done)" : "var(--s-failed)" }}>{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Section: Runners & Agents ──────────────────────────────────────────

function RunnersSection({ slug }: { slug: string }) {
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api(`/projects/${slug}/agents/active`).then((data: any) => {
      setAgents(data.agents ?? []);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [slug]);

  return (
    <div style={SECTION}>
      <div style={{ ...LABEL, marginBottom: 14, fontSize: 11 }}>Runners & Agents</div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 14, marginBottom: 14 }}>
        {[
          { id: "gemini_cli", label: "Gemini CLI", icon: "G", color: "#4285f4" },
          { id: "claude_code", label: "Claude Code", icon: "C", color: "#d97706" },
          { id: "cursor_cli", label: "Cursor Agent", icon: "A", color: "#0ea5e9" },
          { id: "jules", label: "Jules", icon: "J", color: "#16a34a" },
          { id: "codex_cli", label: "Codex CLI", icon: "X", color: "#8b5cf6" },
        ].map(r => (
          <div key={r.id} style={{
            border: "1px solid var(--border)", padding: "10px 12px",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{
              width: 24, height: 24, borderRadius: 4,
              background: r.color, color: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700,
            }}>{r.icon}</span>
            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: "var(--fg)" }}>{r.label}</div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>{r.id}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={LABEL}>Active agents</div>
      {loading ? (
        <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>Loading…</div>
      ) : agents.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>No agents currently running.</div>
      ) : (
        <div>
          {agents.map((a: any, i: number) => (
            <div key={i} style={{
              padding: "6px 10px", borderBottom: "1px solid var(--border)",
              display: "flex", gap: 12, alignItems: "center",
            }}>
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 600, color: "var(--fg)" }}>
                {a.role}
              </span>
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                {a.runner} · {a.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Section: Skills ────────────────────────────────────────────────────

function SkillsSection({ slug }: { slug: string }) {
  const [skills, setSkills] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api(`/projects/${slug}/skills`).then((data: any) => {
      setSkills(data.skills ?? []);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [slug]);

  return (
    <div style={SECTION}>
      <div style={{ ...LABEL, marginBottom: 14, fontSize: 11 }}>Skills</div>

      {loading ? (
        <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>Loading…</div>
      ) : skills.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
          No skills found. Add .md playbook files to <code>agents/skills/</code> in the repo.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {skills.map((s: any, i: number) => (
            <div key={i} style={{
              border: "1px solid var(--border)", padding: "8px 10px",
              background: "var(--bg)",
            }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: "var(--fg)", marginBottom: 2 }}>
                {s.name ?? s.slug ?? s.path ?? `Skill ${i + 1}`}
              </div>
              {s.path && (
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                  {s.path}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Section: Danger Zone ───────────────────────────────────────────────

function DangerSection({ slug }: { slug: string }) {
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared] = useState(false);

  async function clearHydration() {
    setClearing(true);
    try {
      await postJson(`/projects/${slug}/clear-hydration`, {});
      setCleared(true);
      setTimeout(() => setCleared(false), 3000);
    } catch {}
    setClearing(false);
  }

  return (
    <div style={{ ...SECTION, borderBottom: "none" }}>
      <div style={{ ...LABEL, marginBottom: 14, fontSize: 11, color: "var(--s-failed)" }}>Danger Zone</div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, padding: "12px 14px", border: "1px solid var(--s-failed)44", background: "var(--s-failed)08" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--fg)" }}>Clear hydration</div>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
            Resets ontology state. Files on disk are preserved.
          </div>
        </div>
        <button style={BTN_DANGER} onClick={clearHydration} disabled={clearing}>
          {clearing ? "…" : cleared ? "✓ Cleared" : "Clear"}
        </button>
      </div>
    </div>
  );
}

// ── Tab bar ────────────────────────────────────────────────────────────

const TABS = [
  { id: "general", label: "General" },
  { id: "secrets", label: "Secrets" },
  { id: "git", label: "Git & GitHub" },
  { id: "runners", label: "Runners" },
  { id: "skills", label: "Skills" },
  { id: "danger", label: "Danger" },
] as const;

// ── Main Page ──────────────────────────────────────────────────────────

export default function SettingsPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const [tab, setTab] = useState<string>("general");

  return (
    <ProjectShell slug={slug} title="Settings" section="settings">
      <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

        {/* Tab bar */}
        <div style={{
          borderBottom: "1px solid var(--border)",
          padding: "0 16px",
          display: "flex",
          gap: 0,
          background: "var(--panel)",
          flexShrink: 0,
        }}>
          {TABS.map(t => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  background: "none", border: "none",
                  padding: "9px 14px",
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 11, letterSpacing: "0.06em",
                  color: active ? "var(--fg)" : "var(--muted)",
                  fontWeight: active ? 600 : 400,
                  borderBottom: active ? "2px solid var(--fg)" : "2px solid transparent",
                  cursor: "pointer",
                  transition: "color 100ms, border-color 100ms",
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {tab === "general" && <GeneralSection slug={slug} />}
          {tab === "secrets" && <SecretsSection slug={slug} />}
          {tab === "git" && <GitSection slug={slug} />}
          {tab === "runners" && <RunnersSection slug={slug} />}
          {tab === "skills" && <SkillsSection slug={slug} />}
          {tab === "danger" && <DangerSection slug={slug} />}
        </div>
      </div>
    </ProjectShell>
  );
}
