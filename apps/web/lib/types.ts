export type DashboardPanel = {
  id: string;
  title: string;
  description?: string;
  width?: "full" | "half";
  height?: number;
  html: string;
};

export type DashboardResponse = {
  panels: DashboardPanel[];
  projectName: string;
  slug: string;
};

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

export type PlannerApproval = {
  _id?: string;
  taskId?: string | null;
  agentSessionId?: string | null;
  approvalType?: string | null;
  status?: string | null;
  requestedByRole?: string | null;
  grantedByUserId?: string | null;
  requestedAt?: string | null;
  resolvedAt?: string | null;
  resolutionNote?: string | null;
};

export type PlannerDecision = {
  tool?: string | null;
  timestamp?: number | null;
  rationale?: string | null;
  result_summary?: string | null;
  args?: Record<string, unknown> | null;
};

export type PendingQuestion = {
  question_id?: string;
  question?: string;
  status?: string;
  session_id?: string | null;
  role?: string | null;
};

export type PendingDispatch = {
  work_order_id?: string;
  title?: string;
  runner?: string | null;
  runner_name?: string | null;
  role?: string | null;
  task_id?: string | null;
  created_at?: string | null;
  task_payload?: {
    work_order_id?: string;
    task_description?: string;
    role?: string | null;
    branch?: string | null;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export type AutopilotStatus = {
  enabled: boolean;
  autoApprove: boolean;
  active?: boolean;
  dispatchApprovalRequired?: boolean;
};

export type GoalSpend = {
  timeMinutes?: number | null;
  tokens?: number | null;
  apiCostUsd?: number | null;
  retries?: number | null;
};

export type GoalContract = {
  goalId: string;
  objective: string;
  successCriteria: string[];
  requiredEvidence: string[];
  forbiddenShortcuts: string[];
  escalationPolicy: string[];
  allowedSpend: GoalSpend;
  createdAt?: number;
  updatedAt?: number;
  mode?: string;
  markdownPath?: string;
};

export type GoalCriterionStatus = {
  criterion: string;
  satisfied: boolean;
  reason: string;
};

export type GoalState = {
  goalId: string;
  contract?: GoalContract;
  phase: string;
  phaseHistory?: Array<{
    phase: string;
    at: number;
    reason: string;
  }>;
  status: string;
  currentBlocker?: string | null;
  activeFailure?: {
    failureClass: string;
    summary: string;
    at: number;
    retryEligible: boolean;
    retryBudgetRemaining: number;
  } | null;
  lastMeaningfulProgressAt?: number | null;
  autonomyConfidence?: number;
  preflight?: {
    passed: boolean;
    checks: Array<{
      name: string;
      passed: boolean;
      detail: string;
    }>;
    currentBlocker?: string | null;
    lastRunAt?: number | null;
    manifestLoaded?: boolean;
  };
  tracks?: {
    research: { status: string; blocker?: string | null };
    platformRepair: { status: string; blocker?: string | null };
  };
  runCounts?: {
    successful: number;
    failed: number;
  };
  retryBudget?: {
    max: number;
    used: number;
    remaining: number;
  };
  success?: {
    criteriaSatisfied: number;
    criteriaTotal: number;
    percent: number;
    criteria: GoalCriterionStatus[];
  };
  dashboard?: {
    currentPhase?: string;
    currentBlocker?: string | null;
    retryBudgetUsed?: number;
    successfulRuns?: number;
    failedRuns?: number;
    criteriaSatisfiedPercent?: number;
    lastMeaningfulProgressAt?: number | null;
    autonomyConfidence?: number;
    autopilotEnabled?: boolean;
  };
};

export type GoalBundle = {
  contract: GoalContract;
  state: GoalState;
  lessons: Array<Record<string, unknown>>;
  blockers: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  goalMarkdown?: string;
  files?: {
    goalMd?: string;
    goalState?: string;
    goalLessons?: string;
    goalBlockers?: string;
    goalDecisions?: string;
  };
  stateMachine?: {
    version: number;
    phases: Array<Record<string, unknown>>;
  };
};

export type PlannerTaskDraft = {
  title: string;
  description: string;
  status?: string;
  agentRole: string;
  repoPaths?: string[];
  acceptanceCriteria?: string[];
  dependsOnTaskIds?: string[];
  priority?: string | null;
  runner?: string | null;
  approvalState?: string | null;
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
  thinkingSummary?: string | null;
  workingOn?: string | null;
  activeFile?: string | null;
  activeCommand?: {
    name?: string | null;
    preview?: string | null;
    timestamp?: string | null;
    status?: string | null;
  } | null;
  waitingFor?: {
    kind?: string | null;
    summary?: string | null;
    timestamp?: string | null;
  } | null;
  currentActivity?: {
    kind?: string | null;
    label?: string | null;
    summary?: string | null;
    thinkingSummary?: string | null;
    workingOn?: string | null;
    activeFile?: string | null;
    activeCommand?: {
      name?: string | null;
      preview?: string | null;
      timestamp?: string | null;
      status?: string | null;
    } | null;
    waitingFor?: {
      kind?: string | null;
      summary?: string | null;
      timestamp?: string | null;
    } | null;
  } | null;
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
  progress?: {
    closed: number;
    total: number;
  };
  controlPlane?: {
    phase?: string | null;
    nextAction?: string | null;
    snapshotLoaded?: boolean;
  };
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
    description?: string | null;
    gitRepoUrl?: string | null;
    defaultBranch?: string | null;
    agentModel?: string | null;
    githubSyncMode?: string | null;
    localRepoPath?: string | null;
    manifestPath?: string | null;
  };
  repoHealth?: {
    hasLocalRepo?: boolean;
    hasRailYaml?: boolean;
    hasResearchPlan?: boolean;
  } | null;
  autopilot?: AutopilotStatus;
  pendingDispatches?: PendingDispatch[];
  pendingQuestions?: PendingQuestion[];
  decisions?: PlannerDecision[];
  refreshedAt?: number;
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
  controlPlane?: {
    phase?: string | null;
    nextAction?: string | null;
    currentBlocker?: string | null;
    goal?: CommandCenter["goal"] | null;
    taskCounts?: CommandCenter["taskCounts"];
    recentArtifacts?: CommandCenter["recentArtifacts"];
    sourceSummary?: CommandCenter["sourceSummary"];
    skillSummary?: CommandCenter["skillSummary"];
    integritySummary?: CommandCenter["integritySummary"];
    projectReality?: CommandCenter["projectReality"] | null;
    auditors?: CommandCenter["auditors"] | null;
    blockerSummary?: CommandCenter["blockerSummary"];
    repairQueue?: CommandCenter["repairQueue"];
    recommendedRepairTask?: CommandCenter["recommendedRepairTask"];
    closeoutCertificate?: CommandCenter["closeoutCertificate"] | null;
    ontologyFollowUps?: CommandCenter["ontologyFollowUps"];
    missionBrief?: {
      current?: string | null;
      next?: string | null;
      sourceSessionId?: string | null;
      sourceRole?: string | null;
      sourceStatus?: string | null;
      sourceUpdatedAt?: string | null;
    } | null;
    snapshot?: {
      loaded?: boolean;
      path?: string | null;
      generatedAt?: number | null;
      version?: number | null;
    } | null;
  };
};

export type PlannerControlPlaneSnapshot = {
  board: PlannerBoard;
  autopilot: AutopilotStatus;
  goal: GoalBundle | null;
  phase?: string | null;
  nextAction?: string | null;
  currentBlocker?: string | null;
  projectReality?: CommandCenter["projectReality"];
  auditors?: CommandCenter["auditors"];
  closeoutCertificate?: CommandCenter["closeoutCertificate"];
  missionBrief?: CommandCenter["missionBrief"];
  pendingDispatches: PendingDispatch[];
  pendingQuestions: PendingQuestion[];
  decisions: PlannerDecision[];
  snapshot?: CommandCenter["snapshot"];
  refreshedAt: number;
};

export type BlockerCategory =
  | "approval_required"
  | "stale_session"
  | "planner_drift"
  | "hydration_failure"
  | "ontology_health"
  | "integrity_gap"
  | "source_gap"
  | "closeout_pending"
  | "clear";

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
  missionBrief?: {
    current: string;
    next: string;
    sourceSessionId?: string | null;
    sourceRole?: string | null;
    sourceStatus?: string | null;
    sourceUpdatedAt?: string | null;
  } | null;
  nextAction: string;
  goal?: {
    objective?: string | null;
    phase?: string | null;
    currentBlocker?: string | null;
    retryBudget?: GoalState["retryBudget"];
    success?: GoalState["success"];
    dashboard?: GoalState["dashboard"];
    tracks?: GoalState["tracks"];
  } | null;
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
    freshnessCounts?: Record<string, number>;
    admissibilityCounts?: Record<string, number>;
    admissibilityHighlights?: Array<{
      id: string;
      name: string;
      admissibilityStatus: string;
      freshnessStatus: string;
      qualityStatus: string;
    }>;
    notesPath?: string | null;
  };
  skillSummary: {
    count: number;
    agentRolesWithSkillAccess: string[];
  };
  integritySummary?: {
    staleArtifactCount: number;
    sourceFreshnessCounts: Record<string, number>;
    sourceAdmissibilityCounts: Record<string, number>;
    agentWorkflow: AgentWorkflowSummary;
    hypothesisRanking?: Array<{
      id: string;
      computedScore: number;
      scoreBreakdown: {
        evidenceCoverage: number;
        dataReady: number;
        reproducibility: number;
      };
      rankingReasons: string[];
    }>;
  };
  ontologyFollowUps?: {
    path?: string | null;
    questions: Array<{
      title: string;
      classification?: string | null;
      notes?: string[];
      expectedTaskTitle?: string | null;
      taskPresent?: boolean;
      taskStatus?: string | null;
    }>;
    classificationCounts: Record<string, number>;
  };
  auditedTruth?: {
    generatedAt?: string;
    path?: string;
    currentBlocker?: string | null;
    session?: {
      id?: string;
      role?: string;
      status?: string;
      reviewStatus?: string;
      verificationStatus?: string;
      publishStatus?: string;
    };
    planner?: {
      taskCounts?: Record<string, number>;
      readyTasks?: string[];
      blockedTasks?: string[];
      activeTasks?: string[];
    };
    integrity?: {
      action?: string;
      blocked?: boolean;
      reasons?: string[];
    };
  } | null;
  recentAudits?: Array<{
    generatedAt?: string;
    path?: string;
    currentBlocker?: string | null;
    session?: {
      id?: string;
      role?: string;
      status?: string;
      reviewStatus?: string;
      verificationStatus?: string;
      publishStatus?: string;
    };
    integrity?: {
      blocked?: boolean;
      reason?: string | null;
    };
    planner?: {
      blockedTaskCount?: number;
      readyTaskCount?: number;
    };
  }>;
  currentBlocker?: string | null;
  blockerSummary?: {
    blocked: boolean;
    headline: string;
    reasons: string[];
    repairs: string[];
    category?: BlockerCategory;
    categoryLabel?: string;
    severity?: "ok" | "info" | "warning" | "critical" | "action";
    fixSection?: string | null;
    fixHref?: string | null;
  };
  repairQueue?: {
    count: number;
    readyCount: number;
    runningCount: number;
    byStatus: Record<string, number>;
    tasks: Array<{
      id: string;
      title: string;
      status: string;
      agentRole: string;
    }>;
  };
  recommendedRepairTask?: {
    id: string;
    title: string;
    status: string;
    agentRole: string;
    auditor?: string | null;
    reason?: string | null;
  } | null;
  projectReality?: {
    hasDrift: boolean;
    duplicateTaskFileCount: number;
    taskSessionMismatchCount: number;
    staleRuntimeSessionCount: number;
    zombieSessionCount?: number;
    staleAuditSessionCount: number;
    terminalSessionCount: number;
    activeRuntimeSessionCount: number;
    runningAgentStatusDriftCount?: number;
    runningAgentRoleDriftCount?: number;
    runningAgentRunnerDriftCount?: number;
    ontologyArtifactDriftCount?: number;
    artifactRegistryDriftCount?: number;
    secretPolicyRoleDriftCount?: number;
    roleConfigAliasDriftCount?: number;
    details?: {
      duplicateTaskFiles: string[];
      taskSessionMismatchTaskIds: string[];
      staleRuntimeSessionIds: string[];
      zombieSessionIds?: string[];
      staleAuditSessionIds: string[];
      terminalSessionIds: string[];
      activeRuntimeSessionIds: string[];
      runningAgentStatusDrift?: {
        hasDrift: boolean;
        sessions: Array<{
          sessionId: string;
          status: string;
          canonicalStatus: string;
        }>;
      };
      runningAgentRoleDrift?: {
        hasDrift: boolean;
        sessions: Array<{
          sessionId: string;
          role: string;
          canonicalRole: string;
        }>;
      };
      runningAgentRunnerDrift?: {
        hasDrift: boolean;
        sessions: Array<{
          sessionId: string;
          runner: string;
          canonicalRunner: string;
        }>;
      };
      ontologyArtifactDrift?: {
        hasDrift: boolean;
        activeDuckdbPath?: string | null;
        expectedDuckdbPath?: string | null;
        reason?: string | null;
      };
      artifactRegistryDrift?: {
        hasDrift: boolean;
        untrackedArtifactPaths: string[];
        missingArtifactPaths: string[];
      };
      secretPolicyRoleDrift?: {
        hasDrift: boolean;
        policies: Array<{
          policyId: string;
          agentRole: string;
          canonicalRole: string;
          allowedSecretNames: string[];
        }>;
      };
      roleConfigAliasDrift?: {
        hasDrift: boolean;
        configs: Array<{
          configPath: string;
          role: string;
          canonicalRole: string;
        }>;
      };
    };
  };
  auditors?: Record<
    string,
    {
      status: string;
      blockers?: string[];
      state?: string | null;
      stateClassification?: string | null;
    }
  >;
  repoHealth: {
    hasLocalRepo: boolean;
    hasRailYaml: boolean;
    hasResearchPlan: boolean;
  };
  snapshot?: {
    loaded?: boolean;
    path?: string | null;
    generatedAt?: number | null;
    version?: number | null;
  };
  lifecyclePhase?: string;
  closeoutCertificate?: {
    status: "issued" | "pending" | "would_issue_if";
    phase: string;
    headline: string;
    blockers: string[];
  };
};

export type SourceState = {
  freshnessStatus: string;
  qualityStatus: string;
  admissibilityStatus?: string;
  isFresh: boolean;
  isStale: boolean;
  needsRefresh: boolean;
  isBlocked: boolean;
  isAdmissible?: boolean;
};

export type ArtifactTrustState = {
  isTrusted: boolean;
  isBlocked: boolean;
  isStale: boolean;
};

export type AgentWorkflowSection = {
  status: string;
  requirements: string[];
  datasetsMissingProvenance?: string[];
  datasetsMissingFreshness?: string[];
  artifactsMissingLineage?: string[];
  artifactsMissingVerificationCommands?: string[];
  artifactsMissingVerification?: string[];
  artifactsWithUnsupportedClaims?: string[];
  missingEvidenceClaims?: string[];
  staleSources?: string[];
  reproducibilityGaps?: string[];
  failedVerificationRuns?: string[];
};

export type AgentWorkflowSummary = {
  research: AgentWorkflowSection;
  data: AgentWorkflowSection;
  coding: AgentWorkflowSection;
  artifact: AgentWorkflowSection;
  health: AgentWorkflowSection;
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
  origin?: string | null;
  access_method?: string | null;
  freshness_status: string;
  provenance?: Record<string, unknown>;
  retrieved_at?: string | null;
  license?: string | null;
  quality_status: "candidate" | "validated" | "blocked" | "rejected";
  sourceState?: SourceState;
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

export type HypothesisRecord = {
  id: string;
  statement: string;
  scope?: string | null;
  falsifiers: string[];
  status: "draft" | "supported" | "weakened" | "rejected" | "archived";
  score?: number | null;
  parent_id?: string | null;
  claim_keys: string[];
  task_ids: string[];
  artifact_paths: string[];
  human_notes?: string | null;
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
  verificationStatus?: string;
  trustState?: ArtifactTrustState;
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
  hypotheses: HypothesisRecord[];
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
  freshnessStatus?: string;
  qualityStatus?: string;
  sourceState?: SourceState;
};

export type ProjectArtifact = {
  name: string;
  path: string;
  type: string;
  sizeBytes: number;
  modifiedAt: number;
  previewable: boolean;
  promotionState?: string;
  verificationStatus?: string;
  trustState?: ArtifactTrustState;
  assumptions?: string[];
  sources?: string[];
  claims?: string[];
  inputs?: string[];
  scripts?: string[];
  verificationRuns?: string[];
  staleReasons?: string[];
  generatedAt?: string | null;
  preview?: {
    kind: string;
    content?: string;
    rows?: string[][];
    imagePath?: string;
  };
};

export type ProjectIntegrityResponse = {
  indexes: IntegrityIndexes;
  summary: {
    assumptionCount: number;
    sourceCount: number;
    sourceFreshnessCounts: Record<string, number>;
    claimCount: number;
    artifactCount: number;
    staleArtifactCount: number;
    verificationRunCount: number;
    verificationStatusCounts: Record<string, number>;
    promotionStateCounts: Record<string, number>;
  };
  agentWorkflow: AgentWorkflowSummary;
  staleOutputs: ArtifactLineageRecord[];
  hypothesisRanking?: Array<{
    id: string;
    computedScore: number;
    scoreBreakdown: {
      evidenceCoverage: number;
      dataReady: number;
      reproducibility: number;
    };
    rankingReasons: string[];
  }>;
};

export type IntegrityRerunPlan = {
  assumption?: AssumptionRecord;
  assumptions?: AssumptionRecord[];
  affectedArtifacts: ArtifactLineageRecord[];
  affectedPaths: string[];
  stalePaths: string[];
  proposedTasks: Array<{
    title: string;
    description: string;
    agentRole: string;
    repoPaths: string[];
    acceptanceCriteria: string[];
  }>;
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
  approvals: PlannerApproval[];
  blockersPath?: string | null;
  sessions?: RunnerSession[];
};

export type ZenProject = {
  name: string;
  slug: string;
  phase: string;
  health: string;
};

export type ZenActiveRun = {
  id: string;
  label: string;
  role: string;
  runner: string;
  status: string;
  elapsedSeconds: number;
  lastEvent?: string;
  outputsCreated: string[];
  needsInput: boolean;
};

export type ZenTruth = {
  claim: string;
  confidence: number;
  evidenceRefs: string[];
  verified: boolean;
};

export type ZenDecision = {
  id?: string | null;
  type: string;
  severity?: string | null;
  source?: string | null;
  prompt: string;
  recommendedAction?: string;
  actions: Array<Record<string, unknown>>;
};

export type ZenPlan = {
  now: string[];
  next: string[];
  later: string[];
  done: string[];
};

export type ZenAttention = {
  severity: "info" | "warning" | "error";
  title: string;
  detail: string;
  action?: Record<string, unknown>;
};

export type ZenArtifactSummary = {
  name: string;
  path: string;
  freshness: string;
  verified: boolean;
};

export type ZenResponse = {
  project: ZenProject;
  objective: string;
  activeRun?: ZenActiveRun | null;
  latestTruth: ZenTruth[];
  nextDecision?: ZenDecision | null;
  plan: ZenPlan;
  attention: ZenAttention[];
  artifacts: ZenArtifactSummary[];
  decisions?: ZenDecision[];
};
