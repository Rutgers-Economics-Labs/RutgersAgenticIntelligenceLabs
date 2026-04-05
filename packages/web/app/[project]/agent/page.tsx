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
    <div className="flex -m-8 h-screen overflow-hidden bg-[--background]">
      <SessionList
        projectSlug={projectSlug}
        activeSessionId={activeSessionId}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
      />
      <div className="flex flex-1 flex-col min-w-0">
        <header className="flex items-center justify-between px-5 py-3 border-b border-[--border] bg-[--card] shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[--primary]" />
            <span className="text-sm font-semibold text-[--foreground]">AI Research Workspace</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <select
                value={selectedModel}
                onChange={e => setSelectedModel(e.target.value)}
                className="appearance-none bg-[--muted] border border-[--border] rounded-md px-3 py-1.5 text-xs text-[--foreground] pr-7 cursor-pointer focus:outline-none focus:ring-1 focus:ring-[--primary]"
              >
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
              <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-[--muted-foreground] pointer-events-none" />
            </div>
          </div>
        </header>

        <div className="flex flex-1 flex-col overflow-hidden">
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
