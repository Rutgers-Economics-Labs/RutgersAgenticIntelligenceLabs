export type PlannerMessage = {
  role: string;
  content: string;
  messageType?: string;
  timestamp?: string;
};

export type PlannerTask = {
  _id: string;
  title: string;
  description: string;
  status: string;
  agentRole: string;
  approvalState?: string | null;
  runner?: string | null;
  repoPaths?: string[];
  acceptanceCriteria?: string[];
  latestRunSummary?: string | null;
};

export type ReviewSummary = {
  workspacePath?: string | null;
  workspaceBranch?: string | null;
  reviewStatus?: string | null;
  runnerEventCursor?: number | null;
  summaryPath?: string | null;
  diffPath?: string | null;
  todosPath?: string | null;
  verificationPath?: string | null;
};

export type RunnerSession = {
  _id?: string;
  id?: string;
  status: string;
  role?: string;
  title?: string;
  taskId?: string;
  runner?: string;
  externalSessionId?: string | null;
  startedAt?: number;
  sessionPath?: string | null;
  review?: ReviewSummary;
  runnerInfo?: {
    stdout?: string;
    stderr?: string;
    normalized_status?: string;
  };
};

export type RunnerSessionDetail = {
  sessionId: string;
  projectSlug: string;
  status?: string;
  role?: string;
  runner?: string;
  title?: string;
  taskId?: string;
  externalSessionId?: string | null;
  startedAt?: number | string | null;
  endedAt?: number | string | null;
  currentFocus?: string | null;
  workspacePath?: string | null;
  workspaceBranch?: string | null;
  reviewStatus?: string | null;
  reviewFiles?: {
    summaryPath?: string | null;
    diffPath?: string | null;
    todosPath?: string | null;
    verificationPath?: string | null;
    summary?: { path?: string | null; content?: string | null };
    diff?: { path?: string | null; content?: string | null };
    todos?: { path?: string | null; content?: string | null };
    verification?: { path?: string | null; content?: string | null };
  };
  reviewContents?: {
    summary?: string;
    diff?: string;
    todos?: string;
    verification?: string;
  };
  timeline?: Array<Record<string, unknown>>;
  changedFiles?: string[];
  changedFileCount?: number;
  recentCommands?: Array<Record<string, unknown>>;
  recentMessages?: Array<Record<string, unknown>>;
  stdoutTail?: string;
  stderrTail?: string;
  normalizedStatus?: string;
  decisions?: {
    assumptions?: string[];
    blockers?: string[];
    openQuestions?: string[];
  };
};

export type ProjectContext = {
  project: {
    name: string;
    slug: string;
    status?: string | null;
    last_hydrated?: number | null;
  };
  ontology?: Record<string, unknown>;
  data_sources?: Array<Record<string, unknown>>;
  pipelines?: Array<Record<string, unknown>>;
  analysis_plugins?: Array<Record<string, unknown>>;
};

export type HydrationStatus = {
  state: string;
  deviceId: string;
  pipelineSlug: string;
  hydrationMode: string;
  commitSha?: string | null;
  manifestFingerprint?: string | null;
  reusableArtifact?: Record<string, unknown> | null;
  currentDeviceArtifacts: Array<Record<string, unknown>>;
  otherDeviceArtifacts: Array<Record<string, unknown>>;
  projectRoot: string;
  manifestPath: string;
};

export type ProjectCatalogItem = {
  name: string;
  slug: string;
  description: string;
  repoUrl: string;
  directory: string;
  localRepoPath: string;
  localExists: boolean;
  manifestExists: boolean;
  needsClone: boolean;
  backendProject?: {
    _id?: string;
    id?: string;
    slug?: string;
    name?: string;
    localRepoPath?: string | null;
    status?: string | null;
  } | null;
  error?: string;
};

export type ProjectCatalogResponse = {
  projects: ProjectCatalogItem[];
};

export type CatalogActivationResponse = {
  status: string;
  project?: Record<string, unknown> | null;
  catalogProject?: ProjectCatalogItem;
};

export type HydrationRerunResponse = {
  jobId: string;
  status: string;
  source?: string;
  pipelineSlug: string;
  projectSlug: string;
  device?: Record<string, unknown>;
};

export type ProjectApprovals = {
  approvals: Array<Record<string, unknown>>;
};

export type RepoEntry = {
  name: string;
  path: string;
  kind: "file" | "directory";
  extension?: string | null;
};

export type RepoPathResponse =
  | {
      path: string;
      kind: "directory";
      entries: RepoEntry[];
    }
  | {
      path: string;
      kind: "file";
      syntaxKind?: string;
      extension?: string;
      sizeBytes?: number;
      content: string;
    };

export type OntologyClassesResponse = {
  classes?: unknown[];
  error?: string;
};

export type PlannerHome = {
  project?: {
    id: string;
    name: string;
    slug: string;
    status?: string | null;
    localRepoPath?: string | null;
    manifestPath?: string | null;
  };
  planner: {
    threadId: string;
    messages: PlannerMessage[];
    board?: Record<string, unknown>;
    tasks: PlannerTask[];
    approvals: Array<Record<string, unknown>>;
    files?: {
      currentPlan?: string | null;
      taskBoard?: string | null;
      approvals?: string | null;
      blockers?: string | null;
    };
    workspaceReview?: {
      sessionsRoot?: string | null;
      sessions?: Array<Record<string, unknown>>;
    };
    sessions?: RunnerSession[];
  };
};

export type CommandCenter = {
  project: {
    id: string;
    name: string;
    slug: string;
    status?: string | null;
    localRepoPath?: string | null;
    defaultBranch?: string | null;
  };
  currentPlan: {
    path?: string | null;
    summary?: string;
    content?: string;
  };
  nextAction: string;
  taskCounts: {
    total: number;
    byStatus: Record<string, number>;
  };
  activeSessions: RunnerSession[];
  pendingApprovals: Array<Record<string, unknown>>;
  recentArtifacts: ProjectArtifact[];
  sourceSummary: {
    count: number;
    statusCounts: Record<string, number>;
    notesPath?: string | null;
  };
  skillSummary: {
    count: number;
    agentRolesWithSkillAccess: string[];
  };
  repoHealth: {
    hasLocalRepo: boolean;
    hasRailYaml: boolean;
    hasResearchPlan: boolean;
  };
};

export type AssumptionRecord = {
  assumption_key: string;
  title: string;
  value: string;
  status: "active" | "needs_review" | "superseded" | "rejected";
  source_path: string;
  affected_paths: string[];
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type SourceRecord = {
  source_key: string;
  source_type: string;
  title: string;
  url_or_path: string;
  retrieved_at?: string | null;
  license?: string | null;
  quality_status: "candidate" | "validated" | "blocked" | "rejected";
  source_path: string;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ClaimRecord = {
  claim_key: string;
  claim_text: string;
  artifact_path?: string | null;
  evidence_paths: string[];
  status: "draft" | "supported" | "unsupported" | "needs_evidence" | "superseded";
  confidence?: number | null;
  source_path: string;
  caveats: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type ArtifactLineageRecord = {
  artifact_path: string;
  artifact_type: string;
  title: string;
  promotion_state: "exploratory" | "draft" | "needs_evidence" | "partially_verified" | "verified" | "stale" | "blocked";
  inputs: string[];
  scripts: string[];
  sources: string[];
  assumptions: string[];
  claims: string[];
  verification_runs: string[];
  stale_reasons: string[];
  stale_marked_at?: string | null;
  generated_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type VerificationRunRecord = {
  run_id: string;
  task_id?: string | null;
  agent_session_id?: string | null;
  status: "pending" | "passed" | "failed" | "blocked";
  checks: Array<Record<string, unknown>>;
  artifact_paths: string[];
  blockers: string[];
  source_path: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type IntegrityIndexes = {
  assumptions: AssumptionRecord[];
  sources: SourceRecord[];
  claims: ClaimRecord[];
  artifact_lineage: ArtifactLineageRecord[];
  verification_runs: VerificationRunRecord[];
};

export type ProjectSkill = {
  slug: string;
  name: string;
  summary: string;
  path: string;
  content: string;
  usedBy: string[];
};

export type ProjectSource = {
  id: string;
  name: string;
  publisher: string;
  provider: string;
  status: string;
  accessMethod: string;
  geography: string;
  timeCoverage: string;
  updateFrequency: string;
  keyFields: unknown;
  qualityNotes: string;
  linkedFiles: string[];
};

export type ProjectArtifact = {
  name: string;
  path: string;
  type: string;
  sizeBytes: number;
  modifiedAt: number;
  previewable: boolean;
  preview?: {
    kind: string;
    content?: string;
    rows?: string[][];
    imagePath?: string;
  };
};

export type ResearchLaunchPayload = {
  researchQuestion: string;
  audience: string;
  deliverables: string[];
  dataConstraints: string;
  publicOnly: boolean;
  citationStrictness: string;
  approvalBeforeWrites: boolean;
  useSubAgents: boolean;
  preferredAgentRoles: string[];
  workflowPresets: string[];
  notes: string;
};

export type ResearchLaunchPreview = {
  objective: string;
  audience: string;
  deliverables: string[];
  workflowPresets: string[];
  agentWorkBreakdown: Array<{
    title: string;
    description: string;
    agentRole: string;
    status: string;
    repoPaths: string[];
    acceptanceCriteria: string[];
  }>;
  skillsToUse: string[];
  expectedRepoOutputs: string[];
  requiredApprovals: string[];
  knownRisks: string[];
  missingInputs: string[];
};

export type PlannerBoard = {
  board: Record<string, unknown>;
  tasks: PlannerTask[];
  approvals: Array<Record<string, unknown>>;
  blockersPath?: string | null;
  sessions?: RunnerSession[];
};
