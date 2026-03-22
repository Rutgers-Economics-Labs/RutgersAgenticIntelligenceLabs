import { render, screen } from "@testing-library/react";
import JobDetailPage from "@/app/(dashboard)/jobs/[id]/page";

const useQueryMock = vi.fn();

vi.mock("convex/react", () => ({
  useQuery: (...args: unknown[]) => useQueryMock(...args),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "job_1" }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/convex/_generated/api", () => ({
  api: {
    jobs: {
      get: "jobs.get",
      getLogs: "jobs.getLogs",
    },
  },
}));

describe("JobDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useQueryMock.mockImplementation((query: string) => {
      if (query === "jobs.get") {
        return {
          _id: "job_1",
          pipelineSlug: "nj_hydration",
          status: "success",
          createdAt: Date.now() - 5_000,
          startedAt: Date.now() - 4_000,
          finishedAt: Date.now() - 1_000,
          outputDbPath: "artifacts/onto.duckdb",
          outputOwlPath: "artifacts/populated_ontology.owl",
          stepResults: [
            {
              stepName: "load_counties",
              status: "done",
              rowCount: 21,
              startedAt: Date.now() - 4_000,
              finishedAt: Date.now() - 3_000,
            },
          ],
        };
      }
      if (query === "jobs.getLogs") {
        return [
          {
            _id: "log_1",
            seq: 1,
            level: "info",
            message: "[job] Starting hydration",
            timestamp: Date.now() - 4_000,
          },
        ];
      }
      return undefined;
    });
  });

  it("renders step timeline, logs, and output links", () => {
    render(<JobDetailPage />);

    expect(screen.getByText("nj_hydration")).toBeInTheDocument();
    expect(screen.getByText("Step Timeline")).toBeInTheDocument();
    expect(screen.getByText("load_counties")).toBeInTheDocument();
    expect(screen.getByText("[job] Starting hydration")).toBeInTheDocument();
    expect(screen.getByText("Explore Data")).toBeInTheDocument();
    expect(screen.getByText("Open SQL")).toBeInTheDocument();
    expect(screen.getByText("Open in Workspace")).toBeInTheDocument();
  });
});
