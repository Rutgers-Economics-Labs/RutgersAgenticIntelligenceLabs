import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ExplorerPage from "@/app/(dashboard)/explorer/page";

const classesMock = vi.fn();
const instancesMock = vi.fn();
const semanticSearchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("projectSlug=test-project"),
}));

vi.mock("convex/react", () => ({
  useQuery: () => ({ pipelineConfigSlug: "test-pipeline" }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/lib/api", () => ({
  ontology: {
    classes: (...args: unknown[]) => classesMock(...args),
    instances: (...args: unknown[]) => instancesMock(...args),
    semanticSearch: (...args: unknown[]) => semanticSearchMock(...args),
  },
}));

describe("ExplorerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    classesMock.mockResolvedValue([
      { name: "County", instanceCount: 21 },
      { name: "Municipality", instanceCount: 564 },
    ]);
    instancesMock.mockResolvedValue({
      total: 1,
      page: 1,
      limit: 50,
      items: [
        {
          id: "County_Hudson",
          iri: "http://example.org/County_Hudson",
          class: "County",
          properties: { hasName: "Hudson County", hasPopulation: 724854 },
        },
      ],
    });
    semanticSearchMock.mockResolvedValue([
      {
        id: "County_Monmouth",
        iri: "http://example.org/County_Monmouth",
        class: "County",
        properties: { hasName: "Monmouth County", hasPopulation: 643615 },
      },
    ]);
  });

  it("switches to semantic search and shows ranked results without pagination", async () => {
    render(<ExplorerPage />);

    expect(await screen.findByText("Hudson County")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Semantic"));
    fireEvent.change(screen.getByPlaceholderText("Search by meaning…"), {
      target: { value: "coastal counties" },
    });

    await waitFor(() => {
      expect(semanticSearchMock).toHaveBeenCalledWith("coastal counties", ["Municipality"], 20, "test-project");
    });

    expect(await screen.findByText("Monmouth County")).toBeInTheDocument();
    expect(screen.queryByText(/Page 1 of/)).not.toBeInTheDocument();
  });

  it("shows a semantic-search error without breaking the page", async () => {
    semanticSearchMock.mockRejectedValueOnce(new Error("service unavailable"));

    render(<ExplorerPage />);

    expect(await screen.findByText("Hudson County")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Semantic"));
    fireEvent.change(screen.getByPlaceholderText("Search by meaning…"), {
      target: { value: "coastal counties" },
    });

    expect(await screen.findByText("Semantic search is unavailable.")).toBeInTheDocument();
    expect(screen.getByText("No results.")).toBeInTheDocument();
  });
});
