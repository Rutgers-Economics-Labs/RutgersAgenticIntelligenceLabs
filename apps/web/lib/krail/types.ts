export type KrailArea = "explore" | "analyze" | "evidence" | "workflows" | "control-plane";

export type KrailViewState = "ready" | "loading" | "error" | "empty";

export type HealthStatus = "healthy" | "attention" | "blocked";

export interface ProjectHealth {
  status: HealthStatus;
  score: number;
  updatedAt: string;
  summary: string;
  metrics: Array<{
    label: string;
    value: string;
    detail: string;
    tone: "positive" | "neutral" | "warning";
  }>;
}

export interface ProvenanceItem {
  id: string;
  title: string;
  source: string;
  retrievedAt: string;
  status: "verified" | "review" | "stale";
  note: string;
}

export interface KrailActivity {
  id: string;
  timestamp: string;
  title: string;
  description: string;
  area: KrailArea;
}

export interface KrailPanel {
  eyebrow: string;
  title: string;
  description: string;
  primaryLabel: string;
  rows: Array<{ label: string; value: string; status?: string }>;
}

export interface KrailPreviewModel {
  project: {
    name: string;
    slug: string;
    description: string;
  };
  health: ProjectHealth;
  panels: Record<KrailArea, KrailPanel>;
  activity: KrailActivity[];
  provenance: ProvenanceItem[];
}

export interface KrailPreviewAdapter {
  getPreview(): Promise<KrailPreviewModel>;
}
