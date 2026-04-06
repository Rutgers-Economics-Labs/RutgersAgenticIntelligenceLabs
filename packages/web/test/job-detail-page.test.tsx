import { render, screen } from "@testing-library/react";
import JobDetailPage from "@/app/[project]/jobs/[id]/page";

const useQueryMock = vi.fn();

vi.mock("convex/react", () => ({
  useQuery: (...args: unknown[]) => useQueryMock(...args),
}));

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react");
  return {
    ...actual,
    use: (p: Promise<{ project: string; id: string }>) => {
      // Mirror React `use()` for the params Promise in tests.
      if (p && typeof (p as Promise<{ project: string; id: string }>).then === "function") {
        return { project: "demo", id: "job_1" };
      }
      return { project: "demo", id: "job_1" };
    },
  };
});

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
    executions: {
      get: "executions.get",
    },
    configs: {
      getPipeline: "configs.getPipeline",
    },
  },
}));

const jobDoc = {
  _id: "job_1",
  pipelineSlug: "nj-hydration",
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

const logLines = [
  {
    _id: "log_1",
    seq: 1,
    level: "info",
    message: "[job] Starting hydration",
    timestamp: Date.now() - 4_000,
  },
];

describe("JobDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    let n = 0;
    useQueryMock.mockImplementation(() => {
      n += 1;
      if (n === 1) return jobDoc;
      if (n === 2) return null;
      if (n === 3) return { parsedSpec: { steps: [{}, {}, {}] } };
      if (n === 4) return logLines;
      return undefined;
    });
  });

  it("renders step timeline, logs, and output links", () => {
    render(<JobDetailPage params={Promise.resolve({ project: "demo", id: "job_1" })} />);

    expect(screen.getByText("nj-hydration")).toBeInTheDocument();
    expect(screen.getByText("Pipeline Execution Timeline")).toBeInTheDocument();
    expect(screen.getByText("1/3 Steps")).toBeInTheDocument();
    expect(screen.getByText("load_counties")).toBeInTheDocument();
    expect(screen.getByText("[job] Starting hydration")).toBeInTheDocument();
    expect(screen.getByText("Explore Knowledge Graph")).toBeInTheDocument();
    expect(screen.getByText("Execution SQL Explorer")).toBeInTheDocument();
    expect(screen.getByText("Research Workspace")).toBeInTheDocument();
  });
});
