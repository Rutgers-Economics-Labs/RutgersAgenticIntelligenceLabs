import { fetchPendingQa, fetchPlannerThread } from "@/lib/api";
import AgentClient from "./client";

type AgentPageProps = {
  params: Promise<{ slug: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

type ChatSeedMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export default async function AgentPage({ params, searchParams }: AgentPageProps) {
  const { slug } = await params;
  const resolvedSearchParams = (await searchParams) ?? {};
  const welcome = resolvedSearchParams.welcome === "1";
  const prompt = typeof resolvedSearchParams.prompt === "string" ? resolvedSearchParams.prompt : "";
  const panel = resolvedSearchParams.panel === "inbox" ? "inbox" : "chat";

  let initialMessages: ChatSeedMessage[] = [];
  let initialHistory: unknown[] = [];
  let initialPendingQuestions: any[] = [];
  let initialThreadLoaded = false;

  if (welcome) {
    initialMessages = [
      {
        id: "welcome",
        role: "assistant",
        content: `I've set up your new project **${slug}** — a GitHub repo has been created and the initial ontology, pipeline, and data sources have been scaffolded.\n\nWhat would you like to research first? I can discover data sources, run a pipeline to populate the ontology, and start analysing once data is loaded.`,
      },
    ];
    initialThreadLoaded = true;
  } else {
    const [threadResult, pendingResult] = await Promise.allSettled([
      fetchPlannerThread(slug),
      fetchPendingQa(slug),
    ]);

    if (threadResult.status === "fulfilled") {
      const raw = Array.isArray(threadResult.value.messages) ? threadResult.value.messages : [];
      initialMessages = raw
        .filter((message: any) => message?.role === "user" || message?.role === "assistant")
        .map((message: any, index: number) => ({
          id: `hist-${index}`,
          role: message.role as "user" | "assistant",
          content: String(message.content ?? ""),
        }));
      initialHistory = raw.filter((message: any) => message?.role === "user" || message?.role === "assistant");
      initialThreadLoaded = true;
    }

    if (pendingResult.status === "fulfilled") {
      initialPendingQuestions = pendingResult.value;
    }
  }

  return (
    <AgentClient
      slug={slug}
      initialMessages={initialMessages}
      initialHistory={initialHistory}
      initialPendingQuestions={initialPendingQuestions}
      initialPanel={panel}
      initialIncomingPrompt={prompt}
      initialWelcome={welcome}
      initialThreadLoaded={initialThreadLoaded}
    />
  );
}
