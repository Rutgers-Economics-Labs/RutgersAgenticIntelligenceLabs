import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkspacePage from "@/app/(dashboard)/workspace/page";

const useQueryMock = vi.fn();
const useMutationMock = vi.fn();
const pushMock = vi.fn();

const agentModelsMock = vi.fn();
const sqlSchemaMock = vi.fn();

vi.mock("convex/react", () => ({
  useQuery: (...args: unknown[]) => useQueryMock(...args),
  useMutation: (...args: unknown[]) => useMutationMock(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => ({ get: () => null }),
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
    chat: vi.fn(),
  },
  sql: {
    schema: (...args: unknown[]) => sqlSchemaMock(...args),
  },
}));

describe("WorkspacePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useQueryMock.mockImplementation((query: string, args: unknown) => {
      if (query === "agent.listSessions") return [];
      if (query === "agent.getSession" && args === "skip") return undefined;
      return undefined;
    });
    useMutationMock.mockReturnValue(vi.fn());
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
});
