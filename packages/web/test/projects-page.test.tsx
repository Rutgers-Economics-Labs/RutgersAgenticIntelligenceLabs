import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ProjectsPage from "@/app/(dashboard)/projects/page";

const useQueryMock = vi.fn();
const useMutationMock = vi.fn();

const forkProjectMock = vi.fn();
const removeProjectMock = vi.fn();
const createProjectMock = vi.fn();

vi.mock("convex/react", () => ({
  useQuery: (...args: unknown[]) => useQueryMock(...args),
  useMutation: (...args: unknown[]) => useMutationMock(...args),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/convex/_generated/api", () => ({
  api: {
    projects: {
      list: "projects.list",
      create: "projects.create",
      forkProject: "projects.forkProject",
      remove: "projects.remove",
    },
  },
}));

describe("ProjectsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useQueryMock.mockReturnValue([
      {
        _id: "project_1",
        slug: "baseline-project",
        name: "Baseline Project",
        description: "Starting point",
        approach: "data-first",
        ontologyConfigSlug: "core-ontology",
        apiConfigSlugs: ["fred-unemployment"],
        status: "draft",
        updatedAt: Date.now(),
      },
    ]);
    useMutationMock.mockImplementation((mutation: string) => {
      if (mutation === "projects.forkProject") return forkProjectMock;
      if (mutation === "projects.remove") return removeProjectMock;
      if (mutation === "projects.create") return createProjectMock;
      return vi.fn();
    });
    forkProjectMock.mockResolvedValue({});
    removeProjectMock.mockResolvedValue({});
    createProjectMock.mockResolvedValue({});
  });

  it("opens the fork modal and submits a fork request", async () => {
    render(<ProjectsPage />);

    fireEvent.click(screen.getByText("Fork"));
    await screen.findByRole("heading", { name: "Fork Project" });

    const input = screen.getByDisplayValue("Baseline Project (fork)");
    fireEvent.change(input, { target: { value: "Baseline Project Copy" } });
    fireEvent.click(screen.getByRole("button", { name: "Fork Project" }));

    await waitFor(() => {
      expect(forkProjectMock).toHaveBeenCalledWith({
        projectId: "project_1",
        newName: "Baseline Project Copy",
      });
    });
  });
});
