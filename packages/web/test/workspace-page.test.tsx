import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WorkspacePageInner } from "@/app/[project]/agent/page";

const useQueryMock = vi.fn();
const useMutationMock = vi.fn();
const pushMock = vi.fn();

const agentModelsMock = vi.fn();
const sqlSchemaMock = vi.fn();
const chatMock = vi.fn();
const createSessionMock = vi.fn();
const appendMessagesMock = vi.fn();
const updateTitleMock = vi.fn();
const deleteSessionMock = vi.fn();
let sessionParamValue: string | null = null;
let sessionsData: Array<Record<string, unknown>> = [];
let currentSessionData: Record<string, unknown> | null | undefined = undefined;
const projectsContextMock = vi.fn();

async function* streamEvents(events: unknown[]) {
  for (const event of events) {
    yield event;
  }
}

vi.mock("convex/react", () => ({
  useQuery: (...args: unknown[]) => useQueryMock(...args),
  useMutation: (...args: unknown[]) => useMutationMock(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => ({ get: () => sessionParamValue }),
}));

vi.mock("@/convex/_generated/api", () => ({
  api: {
    agent: {
      listByProject: "agent.listByProject",
      getSession: "agent.getSession",
      createSession: "agent.createSession",
      appendMessages: "agent.appendMessages",
      updateTitle: "agent.updateTitle",
      deleteSession: "agent.deleteSession",
    },
  },
}));

vi.mock("@/lib/api", () => ({
  agent: {
    models: (...args: unknown[]) => agentModelsMock(...args),
    chat: (...args: unknown[]) => chatMock(...args),
  },
  sql: {
    schema: (...args: unknown[]) => sqlSchemaMock(...args),
  },
  projects: {
    context: (...args: unknown[]) => projectsContextMock(...args),
  },
}));

describe("AgentPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionParamValue = null;
    sessionsData = [];
    currentSessionData = undefined;
    useQueryMock.mockImplementation((query: string, args: unknown) => {
      if (query === "agent.listByProject") return sessionsData;
      if (query === "agent.getSession" && args === "skip") return undefined;
      if (query === "agent.getSession") return currentSessionData;
      return undefined;
    });
    useMutationMock.mockImplementation((mutation: string) => {
      if (mutation === "agent.createSession") return createSessionMock;
      if (mutation === "agent.appendMessages") return appendMessagesMock;
      if (mutation === "agent.updateTitle") return updateTitleMock;
      if (mutation === "agent.deleteSession") return deleteSessionMock;
      return vi.fn();
    });
    agentModelsMock.mockResolvedValue({
      models: [{ id: "test-model", label: "Test Model" }],
      default: "test-model",
    });
    sqlSchemaMock.mockResolvedValue({
      State: [
        { name: "_id", type: "VARCHAR" },
        { name: "hasPopulation", type: "BIGINT" },
      ],
    });
    projectsContextMock.mockResolvedValue({
      project: { name: "Demo Project", status: "hydrated", agentAllowedActions: null },
      ontology: { classes: [{ name: "State", instance_count: 1 }] },
      data_sources: [{ slug: "fred-unemployment", name: "FRED Unemployment" }],
      pipelines: [{ slug: "demo-pipeline", name: "Demo Pipeline" }],
    });
    chatMock.mockReturnValue(streamEvents([]));
    createSessionMock.mockResolvedValue({ sessionId: "session_1" });
    appendMessagesMock.mockResolvedValue({});
    updateTitleMock.mockResolvedValue({});
    deleteSessionMock.mockResolvedValue({});
  });

  it("inserts a schema-aware prompt when a template is selected", async () => {
    render(<WorkspacePageInner projectSlug="demo-project" />);

    await waitFor(() => {
      expect(sqlSchemaMock).toHaveBeenCalledWith("demo-project");
    });

    fireEvent.click(screen.getByText("Research Templates"));
    fireEvent.click(screen.getByText("Difference-in-differences"));

    const textarea = await screen.findByPlaceholderText(
      "Ask a research question..."
    ) as HTMLTextAreaElement;

    await waitFor(() => {
      expect(textarea.value).toContain("[Schema: State(_id, hasPopulation)]");
    });

    expect(textarea.value).toContain("difference-in-differences");
  });

  it("restores an existing session from the URL param", async () => {
    sessionParamValue = "session_1";
    sessionsData = [
      {
        _id: "session_1",
        title: "Saved analysis",
        model: "test-model",
        updatedAt: Date.now(),
      },
    ];
    currentSessionData = {
      _id: "session_1",
      messages: [
        { role: "user", content: "Summarize the data" },
        { role: "assistant", content: "Here is the saved summary." },
      ],
    };

    render(<WorkspacePageInner projectSlug="demo-project" />);

    expect(await screen.findByText("Summarize the data")).toBeInTheDocument();
    expect(screen.getByText("Here is the saved summary.")).toBeInTheDocument();
    expect(createSessionMock).not.toHaveBeenCalled();
  });

  it("creates and persists a new session after the first completed turn", async () => {
    chatMock.mockReturnValue(
      streamEvents([
        { type: "text_delta", content: "There are 2 rows in the sample." },
        {
          type: "done",
          new_messages: [
            { role: "user", content: "How many rows are there?" },
            { role: "assistant", content: "There are 2 rows in the sample." },
          ],
        },
      ])
    );

    render(<WorkspacePageInner projectSlug="demo-project" />);

    const textarea = await screen.findByPlaceholderText(
      "Ask a research question..."
    );

    fireEvent.change(textarea, { target: { value: "How many rows are there?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => {
      expect(createSessionMock).toHaveBeenCalledWith({
        title: "How many rows are there?",
        model: "test-model",
        projectSlug: "demo-project",
      });
    });

    expect(chatMock).toHaveBeenCalledWith("How many rows are there?", [], "test-model", "demo-project");
    expect(pushMock).toHaveBeenCalledWith("/demo-project/agent?session=session_1");

    await waitFor(() => {
      expect(appendMessagesMock).toHaveBeenCalledWith({
        sessionId: "session_1",
        messages: [
          { role: "user", content: "How many rows are there?" },
          { role: "assistant", content: "There are 2 rows in the sample." },
        ],
      });
    });

    expect(updateTitleMock).toHaveBeenCalledWith({
      sessionId: "session_1",
      title: "There are 2 rows in the sample.",
    });
  });
});
