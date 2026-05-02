"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchZenMode } from "@/lib/api";
import { ZenResponse } from "@/lib/types";
import { 
  CheckCircle, 
  AlertCircle, 
  Clock, 
  Pause, 
  Check, 
  Search, 
  Menu,
  ChevronRight,
  Database,
  FileText,
  Activity
} from "lucide-react";
import { clsx } from "clsx";
import { StatusPill } from "@/components/status-pill";

export default function ZenModePage() {
  const { slug } = useParams() as { slug: string };
  const [data, setData] = useState<ZenResponse | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("evidence");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetchZenMode(slug);
        setData(res);
      } catch (err) {
        console.error("Zen fetch failed", err);
      } finally {
        setLoading(false);
      }
    }
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [slug]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--bg)]">
        <div className="rail-label animate-pulse">Entering Zen Mode...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[var(--bg)] space-y-4">
        <div className="text-red-500 font-bold rail-label">Project load failed</div>
        <Link href={`/projects/${slug}`} className="text-xs underline rail-label opacity-60">Return to Overview</Link>
      </div>
    );
  }

  const { project, objective, activeRun, latestTruth, nextDecision, plan, attention, artifacts } = data;

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--fg)]">
      {/* ── Main Content Area ─────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        
        {/* Top Bar (RAIL Minimalist Style) */}
        <header style={{
          height: 40,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--panel)",
        }}>
          <div className="flex items-center gap-4">
            <Link href="/" style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <img
                src="/rel-logo.jpeg"
                alt="REL"
                style={{ width: 24, height: 24, objectFit: "contain", background: "#fff", border: "1px solid var(--border)" }}
              />
              <span className="rail-label" style={{ fontSize: 11 }}>RAIL</span>
            </Link>
            <span style={{ color: "var(--border)" }}>·</span>
            <span className="rail-label" style={{ fontSize: 10, color: "var(--muted)" }}>{slug}</span>
            <span style={{ color: "var(--border)" }}>·</span>
            <div className="flex items-center gap-2">
              <span className="rail-label text-[9px] opacity-60">Phase</span>
              <span className="text-[11px] font-bold uppercase tracking-wider">{project.phase}</span>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
             <div className="flex items-center gap-2">
              <span className="rail-label text-[9px] opacity-60">Health</span>
              <StatusPill value={project.health} />
            </div>
            <span style={{ color: "var(--border)" }}>·</span>
            <Link 
              href={`/projects/${slug}`}
              style={{
                border: "1px solid var(--border-strong)",
                padding: "3px 10px",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--fg)",
              }}
            >
              Exit Zen
            </Link>
          </div>
        </header>

        {/* Main Reading Flow */}
        <main className="flex-1 overflow-y-auto pb-40 scroll-smooth">
          <div className="max-w-2xl mx-auto px-6 py-24 space-y-24">
            
            {/* Objective Section (Serif Content) */}
            <section className="space-y-6">
              <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">Objective</div>
              <h1 
                className="text-4xl font-semibold leading-tight tracking-tight text-[var(--fg)]"
                style={{ fontFamily: "Lora, Georgia, serif" }}
              >
                {objective}
              </h1>
            </section>

            {/* Next Decision (Action Card) */}
            {nextDecision && (
              <section className="space-y-6">
                <div className="rail-label text-[var(--accent)] font-bold tracking-[0.2em]">Attention Required</div>
                <div 
                   className="p-8 rail-panel shadow-lg space-y-6"
                   style={{ borderLeft: "3px solid var(--accent)", borderRadius: 0 }}
                >
                  <div className="flex items-start gap-6">
                    <div className="p-3 bg-[var(--accent)] text-white">
                      <AlertCircle size={24} />
                    </div>
                    <div className="space-y-2">
                      <div className="font-bold text-xl leading-snug">{nextDecision.prompt}</div>
                      <div className="text-sm opacity-70">A project decision is pending your review.</div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-3 pt-2">
                    {nextDecision.actions.map((action: any, idx: number) => (
                      <button 
                        key={idx}
                        className={clsx(
                          "px-6 py-2.5 font-mono text-[10px] font-bold uppercase tracking-widest transition-all",
                          action.value === "approve" ? "bg-[var(--fg)] text-[var(--bg)]" : "bg-[var(--panel-alt)] border border-[var(--border)]"
                        )}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            )}

            {/* Active Run (Agent Card) */}
            <section className="space-y-8">
              <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">Active Agent</div>
              {activeRun ? (
                <div className="rail-panel shadow-sm space-y-0" style={{ borderRadius: 0 }}>
                  <div className="p-6 flex items-center justify-between border-b border-[var(--border)]">
                    <div className="flex items-center gap-5">
                      <div className="w-10 h-10 border border-[var(--border)] bg-[var(--panel-alt)] flex items-center justify-center text-[var(--fg)]">
                        <Activity size={20} />
                      </div>
                      <div>
                        <div className="font-bold text-base leading-none">{activeRun.label}</div>
                        <div className="text-[10px] opacity-40 font-mono uppercase tracking-widest mt-2">{activeRun.role} • {activeRun.runner}</div>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <StatusPill value={activeRun.status} />
                      <div className="flex items-center gap-1.5 text-[9px] font-mono opacity-50 uppercase tracking-tighter">
                        <Clock size={10} />
                        {Math.floor(activeRun.elapsedSeconds / 60)}:{(activeRun.elapsedSeconds % 60).toString().padStart(2, '0')} elapsed
                      </div>
                    </div>
                  </div>
                  
                  <div className="p-6 bg-[var(--panel-alt)] font-mono text-[11px] leading-relaxed opacity-80 overflow-hidden">
                    <span className="opacity-30 mr-2 uppercase tracking-tighter">Output Trace:</span>
                    {activeRun.lastEvent || "Agent is thinking..."}
                  </div>
                  
                  <div className="p-4 flex items-center gap-3 border-t border-[var(--border)]">
                    <button className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider px-5 py-2 bg-[var(--panel)] border border-[var(--border)] hover:bg-[var(--panel-alt)]">
                      <Pause size={12} /> Pause
                    </button>
                    <Link
                      href={`/projects/${slug}/runs/${encodeURIComponent(activeRun.id)}`}
                      className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider px-5 py-2 bg-[var(--panel)] border border-[var(--border)] hover:bg-[var(--panel-alt)]"
                    >
                      Inspect
                    </Link>
                  </div>
                </div>
              ) : (
                 <div className="p-16 border border-dashed border-[var(--border)] flex flex-col items-center justify-center text-center space-y-4 opacity-40">
                   <div className="opacity-20"><CheckCircle size={40} /></div>
                   <div className="rail-label text-[10px]">Awaiting Agent Activation</div>
                 </div>
              )}
            </section>

            {/* Truth Items (Operational Log Style) */}
            <section className="space-y-10">
              <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">Latest Findings</div>
              <div className="border-t border-[var(--border)]">
                {latestTruth.length > 0 ? latestTruth.map((truth, idx) => (
                  <div key={idx} className="activity-row" style={{ gridTemplateColumns: "100px 1fr", padding: "20px 0" }}>
                    <div className="activity-ts flex flex-col items-start gap-2 pr-4">
                       <StatusPill value={truth.verified ? "verified" : "candidate"} />
                       <div className="text-[9px] opacity-40 font-mono font-bold tracking-tighter">{Math.round(truth.confidence * 100)}% CONFIDENCE</div>
                    </div>
                    <div className="activity-content space-y-4">
                      <div 
                        className="text-lg leading-relaxed text-[var(--fg)]"
                        style={{ fontFamily: "Lora, Georgia, serif" }}
                      >
                        {truth.claim}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {truth.evidenceRefs.map((ref, ridx) => (
                          <div key={ridx} className="text-[9px] font-mono bg-[var(--panel-alt)] border border-[var(--border)] px-2.5 py-1 opacity-60 hover:opacity-100 cursor-pointer transition-opacity">
                            {ref.split('/').pop()}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )) : (
                  <div className="py-20 text-center text-[10px] opacity-40 font-mono uppercase tracking-[0.2em]">
                    No research claims finalized.
                  </div>
                )}
              </div>
            </section>

            {/* General Attention Items */}
            {attention.length > 0 && (
              <section className="space-y-6">
                <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">System State</div>
                <div className="space-y-0 border-t border-[var(--border)]">
                  {attention.map((item, idx) => (
                    <div key={idx} className="flex items-start justify-between gap-6 p-4 border-b border-[var(--border)] bg-[var(--panel)]">
                      <div className="space-y-1">
                        <div className="font-bold text-[13px] flex items-center gap-2.5">
                          <span className={clsx(
                            "w-1.5 h-1.5 rounded-full",
                            item.severity === "error" ? "bg-[var(--s-failed)]" : "bg-[var(--s-awaiting)]"
                          )} />
                          {item.title}
                        </div>
                        <div className="text-[12px] opacity-60 ml-4">{item.detail}</div>
                      </div>
                      {item.action && (
                        <button className="flex-shrink-0 px-3 py-1 bg-[var(--panel-alt)] border border-[var(--border)] font-mono text-[10px] font-bold uppercase tracking-wider hover:bg-[var(--border)]">
                          {item.action.label}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

          </div>
        </main>

        {/* Floating Command Palette (Integrated Style) */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 w-full max-w-xl px-4 z-20">
          <div className="rail-panel shadow-2xl p-1.5 flex items-center gap-3 backdrop-blur-lg bg-opacity-90" style={{ borderRadius: 0 }}>
             <div className="pl-4 text-[var(--muted)]"><Search size={18} /></div>
             <input 
               type="text" 
               placeholder="Direct RAIL command..." 
               className="flex-1 bg-transparent border-none outline-none text-[13px] py-2 font-medium placeholder:opacity-30"
             />
             <div className="flex gap-2 pr-1.5">
               <button className="px-4 py-2 bg-[var(--panel-alt)] border border-[var(--border)] font-mono text-[10px] font-bold uppercase tracking-widest hover:bg-[var(--border)]">Pause</button>
               <button className="px-6 py-2 bg-[var(--fg)] text-[var(--bg)] font-mono text-[10px] font-bold uppercase tracking-widest hover:opacity-80 active:scale-95">Send</button>
             </div>
          </div>
        </div>
      </div>

      {/* ── Right Drawer (Matched to App Sidebar) ───────────────────── */}
      <aside 
        style={{
          height: "100%",
          borderLeft: "1px solid var(--border)",
          background: "var(--panel)",
          transition: "width 240ms cubic-bezier(0.4, 0, 0.2, 1)",
          display: "flex",
          flexDirection: "column",
          zIndex: 30,
          width: drawerOpen ? 340 : 40
        }}
      >
        <button 
          onClick={() => setDrawerOpen(!drawerOpen)}
          className="h-10 flex items-center justify-center hover:bg-[var(--panel-alt)] border-b border-[var(--border)] transition-colors"
        >
          {drawerOpen ? <ChevronRight size={16} className="rotate-180 opacity-60" /> : <Menu size={16} className="opacity-60" />}
        </button>
        
        <div className="flex-1 flex overflow-hidden">
          {/* Rail Tab Strip */}
          <div className="w-10 border-r border-[var(--border)] flex flex-col items-center py-8 gap-10 bg-[var(--panel-alt)]">
            <TabIcon active={activeTab === "evidence"} icon={FileText} onClick={() => { setActiveTab("evidence"); setDrawerOpen(true); }} />
            <TabIcon active={activeTab === "plan"} icon={ChevronRight} onClick={() => { setActiveTab("plan"); setDrawerOpen(true); }} />
            <TabIcon active={activeTab === "data"} icon={Database} onClick={() => { setActiveTab("data"); setDrawerOpen(true); }} />
          </div>
          
          {/* Panel Content Area */}
          {drawerOpen && (
            <div className="flex-1 flex flex-col min-w-0">
              <header className="h-10 flex items-center px-5 border-b border-[var(--border)]">
                <span className="rail-label text-[10px] uppercase tracking-[0.2em]">{activeTab}</span>
              </header>
              <div className="flex-1 overflow-y-auto scroll-smooth">
                {activeTab === "evidence" && <EvidenceDrawer artifacts={artifacts} />}
                {activeTab === "plan" && <PlanDrawer plan={plan} />}
                {activeTab === "data" && <DataDrawer />}
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function TabIcon({ active, icon: Icon, onClick }: any) {
  return (
    <button 
      onClick={onClick}
      className={clsx(
        "p-1.5 transition-all relative group",
        active ? "text-[var(--fg)]" : "text-[var(--muted)] hover:text-[var(--fg)]"
      )}
    >
      <Icon size={18} />
      {active && <div className="absolute right-[-14px] top-1/2 -translate-y-1/2 w-[2px] h-4 bg-[var(--fg)]" />}
    </button>
  );
}

function EvidenceDrawer({ artifacts }: { artifacts: any[] }) {
  return (
    <div className="divide-y divide-[var(--border)]">
      <div className="p-4 rail-label text-[9px] opacity-30 uppercase tracking-[0.2em] bg-[var(--panel-alt)]">Provenance Index</div>
      {artifacts.length > 0 ? artifacts.map((a, idx) => (
        <div key={idx} className="p-4 flex items-center justify-between hover:bg-[var(--panel-alt)] transition-all cursor-pointer">
          <div className="min-w-0 pr-4">
            <div className="text-[12px] font-bold truncate tracking-tight">{a.name}</div>
            <div className="text-[9px] opacity-40 truncate font-mono mt-1 uppercase tracking-tighter">{a.path}</div>
          </div>
          <StatusPill value={a.verified ? "verified" : a.freshness} />
        </div>
      )) : (
        <div className="p-10 text-center rail-label text-[9px] opacity-40 italic">No artifacts recorded.</div>
      )}
    </div>
  );
}

function PlanDrawer({ plan }: { plan: any }) {
  return (
    <div className="divide-y divide-[var(--border)]">
      <PlanSection title="Running & Next" tasks={plan.now} active />
      <PlanSection title="Pending" tasks={plan.next} />
      <PlanSection title="Backlog" tasks={plan.later} />
      <PlanSection title="Finalized" tasks={plan.done} completed />
    </div>
  );
}

function PlanSection({ title, tasks, active, completed }: any) {
  if (!tasks || tasks.length === 0) return null;
  return (
    <div>
      <div className="p-3 rail-label text-[9px] opacity-30 uppercase tracking-[0.2em] bg-[var(--panel-alt)]">{title}</div>
      <div className="divide-y divide-[var(--border)]">
        {tasks.map((task: string, idx: number) => (
          <div key={idx} className={clsx(
            "p-4 flex items-start gap-4 transition-all text-[12px]",
            active && "bg-[var(--panel-raised)] border-l-2 border-[var(--fg)]",
            completed && "opacity-40"
          )}>
            <div className="mt-1 flex-shrink-0 opacity-40">
              {completed ? <CheckCircle size={12} /> : <div className={clsx("w-2 h-2 border border-[var(--border)]", active ? "bg-[var(--fg)]" : "bg-transparent")} />}
            </div>
            <div className={clsx("font-medium leading-relaxed tracking-tight", completed && "line-through")}>{task}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DataDrawer() {
  return (
    <div className="p-5 space-y-6">
      <div className="p-5 rail-panel space-y-5" style={{ borderRadius: 0 }}>
        <div className="flex items-center gap-3 font-bold text-[10px] uppercase tracking-[0.2em]">
           <Database size={14} className="opacity-60" />
           Research Schema
        </div>
        <div className="space-y-3 pt-2">
           <div className="flex justify-between text-[10px] font-mono">
             <span className="opacity-40">HEALTH</span>
             <span className="text-[var(--s-running)] font-bold">OPERATIONAL</span>
           </div>
           <div className="flex justify-between text-[10px] font-mono">
             <span className="opacity-40">SYNC_LVL</span>
             <span className="font-bold">92%</span>
           </div>
        </div>
        <div className="h-[1px] w-full bg-[var(--border)] mt-4">
          <div className="h-full bg-[var(--fg)] w-[92%]" />
        </div>
      </div>
    </div>
  );
}
