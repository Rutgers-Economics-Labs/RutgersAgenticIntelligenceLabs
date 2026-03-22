import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import RegistryPage from "@/app/(dashboard)/registry/page";

const registrySearchMock = vi.fn();

vi.mock("@/lib/api", () => ({
  registry: {
    search: (...args: unknown[]) => registrySearchMock(...args),
  },
}));

describe("RegistryPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    registrySearchMock.mockImplementation((query?: string, provider?: string, geography?: string) => {
      const all = [
        {
          provider: "fred",
          id: "UNRATE",
          name: "Unemployment Rate",
          description: "Civilian unemployment rate for the United States.",
          unit: "percent",
          frequency: "monthly",
          geography: "national",
          tags: ["labor", "unemployment"],
          exampleYaml: "name: fred_unrate\ntype: api\nurl: https://fred.example",
          updatedAt: 0,
        },
        {
          provider: "census",
          id: "B01003_001E",
          name: "Total Population",
          description: "ACS total population estimate.",
          unit: "persons",
          frequency: "annual",
          geography: "state",
          tags: ["population"],
          exampleYaml: "name: census_population\ntype: api\nurl: https://census.example",
          updatedAt: 0,
        },
      ];

      return Promise.resolve(all.filter((entry) => {
        if (provider && provider !== "all" && entry.provider !== provider) return false;
        if (geography && geography !== "all" && entry.geography !== geography) return false;
        if (!query) return true;
        return `${entry.name} ${entry.description}`.toLowerCase().includes(String(query).toLowerCase());
      }));
    });
  });

  it("loads search results and builds a use-this link with prefilled YAML", async () => {
    render(<RegistryPage />);

    const matches = await screen.findAllByText("Unemployment Rate");
    expect(matches.length).toBeGreaterThan(0);
    const useThis = screen.getByRole("link", { name: "Use this" });
    expect(useThis).toHaveAttribute("href", expect.stringContaining("/configs?"));
    expect(useThis).toHaveAttribute("href", expect.stringContaining("prefillType=apis"));
    expect(useThis).toHaveAttribute("href", expect.stringContaining("prefillName=Unemployment+Rate"));
  });

  it("filters by provider and geography", async () => {
    render(<RegistryPage />);

    await screen.findAllByText("Unemployment Rate");

    fireEvent.click(screen.getByRole("button", { name: "Census" }));
    fireEvent.change(screen.getByLabelText("Geography filter"), {
      target: { value: "state" },
    });

    await waitFor(() => {
      expect(registrySearchMock).toHaveBeenLastCalledWith("unemployment", "census", "state", 24);
    });
  });
});
