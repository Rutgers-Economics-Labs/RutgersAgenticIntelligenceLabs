"use client";

import { Suspense, useEffect, useState, use } from "react";
import { useQuery } from "convex/react";
import { useRouter, useSearchParams } from "next/navigation";
import { api as convexApi } from "@/convex/_generated/api";
import { agent, ModelInfo, sql, projects } from "@/lib/api";
import { SessionList } from "@/components/agent/SessionList";
import { ContextSnapshot } from "@/components/agent/ContextSnapshot";
import { AgentChat, Message } from "@/components/agent/AgentChat";
import { ChevronDown, Sparkles } from "lucide-react";

function WorkspacePageInner({ projectSlug }: { projectSlug: string }) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [messages, setMessages] = useState<Message[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [schemaSummary, setSchemaSummary] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(undefined);
  const [contextSnapshot, setContextSnapshot] = useState<any>(null);

  const currentSession = useQuery(
    convexApi.agent.getSession,
    activeSessionId ? { sessionId: activeSessionId as any } : "skip"
  );

  useEffect(() => {
    agent.models().then(data => {
      setModels(data.models);
      setSelectedModel(data.default);
    }).catch(() => {});

    sql.schema(projectSlug)
      .then((schema) => {
        const tables = Object.entries(schema).map(([table, columns]) => {
          const cols = columns.map((column) => `${column.name}`).join(", ");
          return `${table}(${cols})`;
        });
        setSchemaSummary(tables.length > 0 ? `[Schema: ${tables.join("; ")}]` : "");
      })
      .catch(() => {});

    projects.context(projectSlug).then(setContextSnapshot).catch(() => {});
  }, [projectSlug]);

  useEffect(() => {
    const sessionParam = searchParams.get("session");
    if (sessionParam) {
      setActiveSessionId(sessionParam);
    } else {
      setActiveSessionId(undefined);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }
    if (currentSession === undefined) return;
    if (!currentSession) {
      setMessages([]);
      return;
    }

    const restoredMessages: Message[] = currentSession.messages
      .filter((msg: any) => msg.role === "user" || msg.role === "assistant")
      .map((msg: any) => ({
        id: Math.random().toString(36).slice(2, 10),
        role: msg.role,
        content: msg.content ?? "",
      }));

    setMessages(restoredMessages);
  }, [activeSessionId, currentSession]);

  const handleSelectSession = (sessionId: string) => {
    setActiveSessionId(sessionId);
    router.push(`/${projectSlug}/agent?session=${sessionId}`);
  };

  const handleNewSession = () => {
    setActiveSessionId(undefined);
    setMessages([]);
    router.push(`/${projectSlug}/agent`);
  };

  const handleSessionCreated = (sessionId: string) => {
    setActiveSessionId(sessionId);
    router.push(`/${projectSlug}/agent?session=${sessionId}`);
  };

  return (
    <div className="flex h-full w-full bg-[--background] overflow-hidden transition-all duration-500">
      <SessionList
        projectSlug={projectSlug}
        activeSessionId={activeSessionId}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
      />
      <div className="flex flex-1 flex-col min-w-0 bg-transparent">
        <header className="h-16 flex items-center justify-between px-8 border-b border-[--border] bg-[--background]/40 shadow-sm backdrop-blur-md shrink-0 relative z-20">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-2xl bg-[--primary]/10 flex items-center justify-center text-[--primary] border border-[--primary]/20 shadow-inner">
               <Sparkles size={20} />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-black uppercase tracking-widest text-[--foreground]">AI Research Assistant</span>
              <span className="text-[10px] text-[--muted-foreground] font-bold uppercase tracking-tighter opacity-60">Session {activeSessionId ? "Active" : "Ready"}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative group">
              <div className="absolute inset-y-0 right-0 flex items-center pr-2.5 pointer-events-none text-[--muted-foreground] group-hover:text-[--primary] transition-colors">
                 <ChevronDown size={14} />
              </div>
              <select
                value={selectedModel}
                onChange={e => setSelectedModel(e.target.value)}
                className="appearance-none bg-[--card]/40 border border-[--border] rounded-xl pl-4 pr-10 py-2.5 text-[11px] font-black uppercase tracking-wider text-[--foreground] hover:bg-[--muted]/60 hover:border-[--primary]/40 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-[--primary]/20"
              >
                {models.map(m => (
                  <option key={m.id} value={m.id} className="bg-[--background] font-sans lowercase tracking-normal">{m.label}</option>
                ))}
              </select>
            </div>
          </div>
        </header>

        <div className="flex flex-1 flex-col overflow-hidden relative">
          <AgentChat
            key={activeSessionId || "new"}
            projectSlug={projectSlug}
            sessionId={activeSessionId}
            messages={messages}
            onMessages={setMessages}
            contextSnapshot={contextSnapshot}
            onContextSnapshot={setContextSnapshot}
            onSessionCreated={handleSessionCreated}
            schemaSummary={schemaSummary}
            models={models}
            selectedModel={selectedModel}
          />
        </div>
      </div>
    </div>
  );
}

export default function WorkspacePage({ params }: { params: Promise<{ project: string }> }) {
  const unwrappedParams = use(params);
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm text-[--muted-foreground]">Loading workspace…</div>}>
      <WorkspacePageInner projectSlug={unwrappedParams.project} />
    </Suspense>
  );
}
