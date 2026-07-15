import type { KrailPreviewAdapter, KrailPreviewModel } from "./types";

const preview: KrailPreviewModel = {
  project: {
    name: "New Jersey Housing Signals",
    slug: "nj-housing-signals",
    description: "A traceable research workspace for housing affordability and supply policy.",
  },
  health: {
    status: "healthy",
    score: 92,
    updatedAt: "Updated 9 minutes ago",
    summary: "Research is reproducible, sources are current, and one decision is ready for review.",
    metrics: [
      { label: "Evidence coverage", value: "84%", detail: "21 of 25 claims linked", tone: "positive" },
      { label: "Workflow health", value: "4 / 5", detail: "One review is waiting", tone: "warning" },
      { label: "Freshness", value: "2h", detail: "Since last source check", tone: "neutral" },
    ],
  },
  panels: {
    explore: {
      eyebrow: "Research landscape",
      title: "Explore the question space",
      description: "Start with entities, geography, and signals before committing to a model or narrative.",
      primaryLabel: "Browse research map",
      rows: [
        { label: "Priority geography", value: "Newark · Jersey City · Camden" },
        { label: "Active signals", value: "Rent burden, permits, vacancies" },
        { label: "Open questions", value: "6" },
      ],
    },
    analyze: {
      eyebrow: "Reasoning workspace",
      title: "Analyze with visible assumptions",
      description: "Compare hypotheses and record the decisions that shape each result.",
      primaryLabel: "Open analysis canvas",
      rows: [
        { label: "Current frame", value: "Affordability pressure" },
        { label: "Model runs", value: "12 reproducible" },
        { label: "Assumptions needing review", value: "1", status: "Review" },
      ],
    },
    evidence: {
      eyebrow: "Research integrity",
      title: "Follow every claim to its source",
      description: "Keep source context, transformations, and verification close to the work they support.",
      primaryLabel: "Review evidence ledger",
      rows: [
        { label: "Verified sources", value: "18" },
        { label: "Claims supported", value: "21 / 25" },
        { label: "Sources to refresh", value: "2", status: "Attention" },
      ],
    },
    workflows: {
      eyebrow: "Operational research",
      title: "Run work that can be repeated",
      description: "Coordinate data preparation, analysis, and review as legible, recoverable workflows.",
      primaryLabel: "Inspect workflow runs",
      rows: [
        { label: "Scheduled workflows", value: "3" },
        { label: "Last successful run", value: "ACS hydration · 09:42" },
        { label: "Waiting for review", value: "Policy brief synthesis", status: "Review" },
      ],
    },
    "control-plane": {
      eyebrow: "Project operations",
      title: "Control the research system",
      description: "See project health, assign responsibility, and make policy decisions with their effects in view.",
      primaryLabel: "Open project controls",
      rows: [
        { label: "Project members", value: "7" },
        { label: "Active agent sessions", value: "2" },
        { label: "Pending approvals", value: "1", status: "Review" },
      ],
    },
  },
  activity: [
    { id: "act-1", timestamp: "09:42", title: "ACS 2024 hydration completed", description: "1,842 county-level observations reconciled against the existing series.", area: "workflows" },
    { id: "act-2", timestamp: "09:18", title: "Claim confidence updated", description: "Rent-burden trend now has two independently verified sources.", area: "evidence" },
    { id: "act-3", timestamp: "Yesterday", title: "Scenario comparison saved", description: "Supply-side policy scenario is ready for collaborator review.", area: "analyze" },
  ],
  provenance: [
    { id: "src-1", title: "American Community Survey 2024", source: "U.S. Census Bureau", retrievedAt: "Today, 09:42", status: "verified", note: "County estimates normalized to the project geography." },
    { id: "src-2", title: "New Jersey building permits", source: "HUD SOCDS", retrievedAt: "Yesterday, 16:20", status: "verified", note: "Monthly permit counts joined at municipality level." },
    { id: "src-3", title: "Rental market snapshot", source: "Local market compilation", retrievedAt: "May 28", status: "review", note: "Citation remains usable; refresh requested before publication." },
  ],
};

/**
 * Explicit temporary boundary for the preview. Replace this adapter with a
 * server-backed implementation once KRAIL contracts are approved.
 */
export const mockKrailPreviewAdapter: KrailPreviewAdapter = {
  async getPreview() {
    return preview;
  },
};
