import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkspacePage from "@/app/(dashboard)/workspace/page";

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
      listSessions: "agent.listSessions",
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
}));

describe("WorkspacePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionParamValue = null;
    sessionsData = [];
    currentSessionData = undefined;
    useQueryMock.mockImplementation((query: string, args: unknown) => {
      if (query === "agent.listSessions") return sessionsData;
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
    chatMock.mockReturnValue(streamEvents([]));
    createSessionMock.mockResolvedValue({ sessionId: "session_1" });
    appendMessagesMock.mockResolvedValue({});
    updateTitleMock.mockResolvedValue({});
    deleteSessionMock.mockResolvedValue({});
  });

  it("inserts a schema-aware prompt when a template is selected", async () => {
    render(<WorkspacePage />);

    await waitFor(() => {
      expect(sqlSchemaMock).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByText("Templates"));
    fireEvent.click(screen.getByText("Difference-in-differences"));

    const textarea = screen.getByPlaceholderText(
      "Ask a research question… (Enter to send, Shift+Enter for newline)"
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

    render(<WorkspacePage />);

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

    render(<WorkspacePage />);

    const textarea = screen.getByPlaceholderText(
      "Ask a research question… (Enter to send, Shift+Enter for newline)"
    );

    fireEvent.change(textarea, { target: { value: "How many rows are there?" } });
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter" });

    expect(await screen.findByText("How many rows are there?")).toBeInTheDocument();
    expect(await screen.findByText("There are 2 rows in the sample.")).toBeInTheDocument();

    await waitFor(() => {
      expect(createSessionMock).toHaveBeenCalledWith({
        title: "How many rows are there?",
        model: "test-model",
      });
    });

    expect(chatMock).toHaveBeenCalledWith("How many rows are there?", [], "test-model");
    expect(pushMock).toHaveBeenCalledWith("/workspace?session=session_1");

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
