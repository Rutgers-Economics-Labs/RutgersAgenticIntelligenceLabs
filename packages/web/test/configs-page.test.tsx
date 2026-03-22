import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ConfigsPage from "@/app/(dashboard)/configs/page";

const useQueryMock = vi.fn();
const modelsMock = vi.fn();
const inferSchemaMock = vi.fn();
const createConfigMock = vi.fn();
const scrapePreviewMock = vi.fn();

vi.mock("convex/react", () => ({
  useQuery: (...args: unknown[]) => useQueryMock(...args),
}));

vi.mock("@/convex/_generated/api", () => ({
  api: {
    configs: {
      listApis: "configs.listApis",
      listOntologies: "configs.listOntologies",
      listPipelines: "configs.listPipelines",
    },
  },
}));

vi.mock("@/lib/api", () => ({
  agent: {
    models: (...args: unknown[]) => modelsMock(...args),
    inferSchema: (...args: unknown[]) => inferSchemaMock(...args),
  },
  configs: {
    create: (...args: unknown[]) => createConfigMock(...args),
    scrapePreview: (...args: unknown[]) => scrapePreviewMock(...args),
    validate: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("ConfigsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useQueryMock.mockImplementation((query: string) => {
      if (query === "configs.listApis") return [];
      if (query === "configs.listOntologies") return [];
      if (query === "configs.listPipelines") return [];
      return [];
    });
    modelsMock.mockResolvedValue({
      models: [{ id: "test-model", label: "Test Model" }],
      default: "test-model",
    });
    inferSchemaMock.mockResolvedValue({
      api_yaml: "name: inferred-api",
      ontology_yaml: "uri: http://example.org/test",
      explanation: "Generated from the provided sample.",
      raw: "",
    });
    createConfigMock.mockResolvedValue({});
    scrapePreviewMock.mockResolvedValue({
      columns: ["county", "population"],
      rows: [
        { county: "Essex", population: "863728" },
        { county: "Hudson", population: "724854" },
      ],
      rowCount: 2,
    });
  });

  it("generates and saves inferred configs", async () => {
    render(<ConfigsPage />);

    fireEvent.click(screen.getByText("✦ Generate from sample"));

    fireEvent.change(screen.getByPlaceholderText("Paste CSV rows or JSON here..."), {
      target: { value: "name,value\nA,1\nB,2" },
    });

    fireEvent.click(screen.getByText("Generate"));

    await screen.findByDisplayValue("name: inferred-api");
    expect(screen.getByDisplayValue("uri: http://example.org/test")).toBeInTheDocument();
    expect(screen.getByText("Generated from the provided sample.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Continue"));
    await screen.findByDisplayValue("Generated API Config");

    fireEvent.click(screen.getByText("Save Both"));

    await waitFor(() => {
      expect(createConfigMock).toHaveBeenCalledTimes(2);
    });
    expect(createConfigMock).toHaveBeenCalledWith(
      "apis",
      expect.objectContaining({ name: "Generated API Config", slug: "generated-api-config" })
    );
    expect(createConfigMock).toHaveBeenCalledWith(
      "ontologies",
      expect.objectContaining({ name: "Generated Ontology Config", slug: "generated-ontology-config" })
    );
  });

  it("previews a scraped table and saves generated scrape configs", async () => {
    inferSchemaMock.mockResolvedValueOnce({
      api_yaml: "name: ignored-by-scrape-flow",
      ontology_yaml: "uri: http://example.org/scraped",
      explanation: "Generated from scraped preview.",
      raw: "",
    });

    render(<ConfigsPage />);

    fireEvent.click(screen.getByText("Scrape URL"));

    fireEvent.change(screen.getByPlaceholderText("https://example.gov/data-table"), {
      target: { value: "https://example.gov/table" },
    });
    fireEvent.change(screen.getByPlaceholderText("table.data-table"), {
      target: { value: "table.data-table" },
    });

    fireEvent.click(screen.getByText("Preview"));

    expect(await screen.findByText("Showing 2 of 2 rows")).toBeInTheDocument();
    expect(scrapePreviewMock).toHaveBeenCalledWith({
      url: "https://example.gov/table",
      table_selector: "table.data-table",
    });

    fireEvent.click(screen.getByText("Generate Config"));

    await screen.findByDisplayValue("uri: http://example.org/scraped");
    expect(await screen.findByDisplayValue(/type: scrape/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Save Both"));

    await waitFor(() => {
      expect(createConfigMock).toHaveBeenCalledTimes(2);
    });
    expect(createConfigMock).toHaveBeenCalledWith(
      "apis",
      expect.objectContaining({
        content: expect.stringContaining("type: scrape"),
      })
    );
    expect(createConfigMock).toHaveBeenCalledWith(
      "ontologies",
      expect.objectContaining({
        content: "uri: http://example.org/scraped",
      })
    );
  });
});
