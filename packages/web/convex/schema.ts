import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  scheduledPipelines: defineTable({
    projectSlug: v.string(),
    pipelineSlug: v.string(),
    cron: v.optional(v.string()),         // resolved cron e.g. "0 * * * *"
    frequency: v.optional(v.string()),    // human shorthand "1h", "daily"
    windowEndsAt: v.optional(v.number()), // ms timestamp, null = indefinite
    enabled: v.boolean(),
    status: v.string(),                   // "active" | "paused" | "completed" | "error"
    lastRunAt: v.optional(v.number()),
    lastJobId: v.optional(v.string()),
    nextRunAt: v.optional(v.number()),
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index("by_project", ["projectSlug"])
    .index("by_status", ["status"]),

  connectorTemplates: defineTable({
    slug: v.string(),
    name: v.string(),
    description: v.string(),
    version: v.string(),
    tags: v.array(v.string()),
    content: v.string(),       // raw YAML (below the --- divider)
    usageCount: v.number(),
    createdBy: v.optional(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index("by_slug", ["slug"]),

  ontologyTemplates: defineTable({
    slug: v.string(),
    name: v.string(),
    description: v.string(),
    version: v.string(),
    tags: v.array(v.string()),
    content: v.string(),       // ontology YAML (classes, properties)
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index("by_slug", ["slug"]),

  apiConfigs: defineTable({
    name: v.string(),
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    sourceType: v.string(),
    isPublic: v.boolean(),
    tags: v.array(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_slug", ["slug"])
    .index("by_public", ["isPublic"]),

  ontologyConfigs: defineTable({
    name: v.string(),
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    ontologyUri: v.string(),
    isPublic: v.boolean(),
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index("by_slug", ["slug"]),

  pipelineConfigs: defineTable({
    name: v.string(),
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    referencedApiSlugs: v.array(v.string()),
    isPublic: v.boolean(),
    tags: v.array(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_slug", ["slug"])
    .index("by_public", ["isPublic"]),

  dataSourceRegistry: defineTable({
    provider: v.string(),
    sourceId: v.string(),
    name: v.string(),
    description: v.string(),
    unit: v.string(),
    frequency: v.string(),
    geography: v.string(),
    tags: v.array(v.string()),
    exampleYaml: v.string(),
    updatedAt: v.number(),
    createdAt: v.number(),
  })
    .index("by_provider", ["provider"])
    .index("by_provider_source", ["provider", "sourceId"]),

  hydrationJobs: defineTable({
    pipelineConfigId: v.id("pipelineConfigs"),
    pipelineSlug: v.string(),
    /** Denormalized slug for API/worker fallback when linking to Convex projectId. */
    projectSlug: v.optional(v.string()),
    projectId: v.optional(v.id("projects")),
    status: v.union(
      v.literal("queued"),
      v.literal("running"),
      v.literal("success"),
      v.literal("failed"),
      v.literal("cancelled"),
    ),
    triggeredBy: v.optional(v.string()),
    startedAt: v.optional(v.number()),
    finishedAt: v.optional(v.number()),
    errorMessage: v.optional(v.string()),
    outputOwlPath: v.optional(v.string()),
    outputDbPath: v.optional(v.string()),
    stepResults: v.array(v.object({
      stepName: v.string(),
      status: v.union(
        v.literal("pending"),
        v.literal("running"),
        v.literal("done"),
        v.literal("failed"),
      ),
      rowCount: v.optional(v.number()),
      errorMessage: v.optional(v.string()),
      startedAt: v.optional(v.number()),
      finishedAt: v.optional(v.number()),
    })),
    createdAt: v.number(),
    machine: v.optional(v.string()),
  })
    .index("by_pipeline", ["pipelineConfigId"])
    .index("by_project", ["projectId", "createdAt"])
    .index("by_status", ["status"])
    .index("by_created", ["createdAt"]),

  projects: defineTable({
    name: v.string(),
    slug: v.string(),
    description: v.optional(v.string()),
    gitRepoUrl: v.optional(v.string()),
    localRepoPath: v.optional(v.string()),
    manifestPath: v.optional(v.string()),
    approach: v.union(v.literal("data-first"), v.literal("ontology-first")),
    ontologyConfigSlug: v.optional(v.string()),
    apiConfigSlugs: v.array(v.string()),
    pipelineConfigSlug: v.optional(v.string()),
    status: v.union(
      v.literal("draft"),
      v.literal("ready"),
      v.literal("hydrated"),
    ),
    lastJobId: v.optional(v.string()),
    // Active knowledge graph artifacts for this project (set after successful hydration).
    // In local mode these are filesystem paths; in S3 mode these are storage keys.
    activeOntologyDbPath: v.optional(v.string()),
    activeOntologyOwlPath: v.optional(v.string()),
    activeOntologyDuckdbPath: v.optional(v.string()),
    activeOntologyEmbeddingsPath: v.optional(v.string()),
    github: v.optional(v.string()),          // "owner/repo" e.g. "rutgers-rail/nj-econ"
    defaultBranch: v.optional(v.string()),   // default "main"
    ontologyTemplates: v.optional(v.array(v.string())),  // slugs of applied templates
    agentModel: v.optional(v.string()),      // LiteLLM model string override
    agentAllowedActions: v.optional(v.array(v.string())),  // allowed tool names
    lastHydratedAt: v.optional(v.number()), // ms timestamp
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_slug", ["slug"])
    .index("by_status", ["status"])
    .index("by_github", ["github"]),

  jobLogs: defineTable({
    jobId: v.string(), // Generic ID (can be hydrationJob or executionJob)
    seq: v.number(),
    level: v.union(v.literal("info"), v.literal("warn"), v.literal("error"), v.literal("stdout"), v.literal("stderr")),
    message: v.string(),
    stepName: v.optional(v.string()),
    timestamp: v.number(),
  })
    .index("by_job", ["jobId"])
    .index("by_job_seq", ["jobId", "seq"]),

  executionJobs: defineTable({
    projectId: v.optional(v.id("projects")),
    workspaceId: v.optional(v.id("workspaces")),
    cellId: v.optional(v.string()),
    hydrationId: v.optional(v.id("hydrationJobs")),
    type: v.union(v.literal("sql"), v.literal("code")),
    input: v.string(),
    status: v.union(
      v.literal("queued"),
      v.literal("running"),
      v.literal("success"),
      v.literal("failed"),
      v.literal("cancelled"),
    ),
    result: v.optional(v.any()), // Final JSON result
    errorMessage: v.optional(v.string()),
    startedAt: v.optional(v.number()),
    finishedAt: v.optional(v.number()),
    createdAt: v.number(),
    machine: v.optional(v.string()),
  })
    .index("by_project", ["projectId", "createdAt"])
    .index("by_workspace_cell", ["workspaceId", "cellId"])
    .index("by_hydration", ["hydrationId"])
    .index("by_status", ["status"])
    .index("by_created", ["createdAt"]),

  // AI agent sessions — stores conversation history
  agentSessions: defineTable({
    projectSlug: v.optional(v.string()),
    title: v.string(),
    model: v.string(),
    messages: v.array(v.object({
      role: v.union(v.literal("user"), v.literal("assistant"), v.literal("tool")),
      content: v.optional(v.string()),
      tool_calls: v.optional(v.any()),
      tool_call_id: v.optional(v.string()),
    })),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_created", ["createdAt"])
    .index("by_project", ["projectSlug", "createdAt"]),

  // Project assistant chat sessions
  projectChats: defineTable({
    projectId: v.id("projects"),
    title: v.string(),
    messages: v.array(v.object({
      role: v.union(v.literal("user"), v.literal("assistant")),
      content: v.string(),
    })),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_project", ["projectId"])
    .index("by_created", ["createdAt"]),

  // Research workspaces — notebook-style cells
  workspaces: defineTable({
    title: v.string(),
    sessionId: v.optional(v.string()),
    pipelineSlug: v.optional(v.string()),
    cells: v.array(v.object({
      id: v.string(),
      type: v.union(
        v.literal("ai-text"),
        v.literal("code"),
        v.literal("sql"),
        v.literal("table"),
        v.literal("chart"),
        v.literal("metric"),
      ),
      content: v.string(),
      result: v.optional(v.any()),
      lastJobId: v.optional(v.string()), // ID of the last execution job
      role: v.optional(v.string()),  // "user" | "assistant" for chat cells
    })),
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index("by_created", ["createdAt"]),

  // Saved analysis scripts for the Analysis Workspace
  analysisScripts: defineTable({
    projectId: v.id("projects"),
    name: v.string(),
    code: v.string(),
    description: v.optional(v.string()),
    lastJobId: v.optional(v.id("executionJobs")),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_project", ["projectId", "createdAt"])
    .index("by_created", ["createdAt"]),

  // Context / Knowledge Base documents
  contextDocuments: defineTable({
    projectId: v.optional(v.id("projects")), // null = global (available to all projects)
    name: v.string(),
    type: v.union(
      v.literal("pdf"),
      v.literal("text"),
      v.literal("url"),
      v.literal("docx"),
    ),
    content: v.string(),       // extracted plain text
    url: v.optional(v.string()),
    fileSize: v.optional(v.number()),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_project", ["projectId", "createdAt"])
    .index("by_created", ["createdAt"]),

  // Ontology snapshots — entity counts saved before/after hydration for diff tracking
  ontologySnapshots: defineTable({
    projectId: v.optional(v.id("projects")),
    label: v.string(),
    tables: v.any(), // { [tableName]: { rowCount, columns: { [col]: { nullRate, distinctCount } } } }
    createdAt: v.number(),
  })
    .index("by_project", ["projectId", "createdAt"])
    .index("by_created", ["createdAt"]),

  // Q&A sessions — persists question+answer history per project
  questionSessions: defineTable({
    projectId: v.optional(v.id("projects")),
    question: v.string(),
    blocks: v.array(v.object({
      kind: v.string(),
      text: v.optional(v.string()),
      name: v.optional(v.string()),
      result: v.optional(v.any()),
      explanation: v.optional(v.string()),
      missing: v.optional(v.string()),
      sources: v.optional(v.array(v.string())),
    })),
    createdAt: v.number(),
  })
    .index("by_project", ["projectId", "createdAt"])
    .index("by_created", ["createdAt"]),

  plannerMessages: defineTable({
    projectId: v.id("projects"),
    sessionId: v.optional(v.string()),
    threadId: v.string(),
    role: v.union(v.literal("user"), v.literal("assistant"), v.literal("system")),
    content: v.string(),
    messageType: v.string(),
    createdAt: v.number(),
  })
    .index("by_project_thread", ["projectId", "threadId", "createdAt"])
    .index("by_project", ["projectId", "createdAt"]),

  taskBoards: defineTable({
    projectId: v.id("projects"),
    sessionId: v.optional(v.string()),
    title: v.string(),
    status: v.string(),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_project", ["projectId", "updatedAt"]),

  tasks: defineTable({
    boardId: v.id("taskBoards"),
    projectId: v.id("projects"),
    sessionId: v.optional(v.string()),
    title: v.string(),
    description: v.string(),
    status: v.string(),
    priority: v.optional(v.string()),
    agentRole: v.string(),
    runner: v.optional(v.string()),
    repoPaths: v.array(v.string()),
    acceptanceCriteria: v.array(v.string()),
    dependsOnTaskIds: v.array(v.id("tasks")),
    approvalState: v.optional(v.string()),
    gitSnapshotPath: v.optional(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_board", ["boardId", "updatedAt"])
    .index("by_project", ["projectId", "updatedAt"])
    .index("by_status", ["status"]),

  taskEvents: defineTable({
    taskId: v.id("tasks"),
    eventType: v.string(),
    payload: v.any(),
    createdAt: v.number(),
  })
    .index("by_task", ["taskId", "createdAt"]),

  approvals: defineTable({
    projectId: v.id("projects"),
    taskId: v.optional(v.id("tasks")),
    agentSessionId: v.optional(v.id("agentSessions")),
    approvalType: v.string(),
    status: v.string(),
    requestedByRole: v.string(),
    grantedByUserId: v.optional(v.string()),
    requestedAt: v.number(),
    resolvedAt: v.optional(v.number()),
  })
    .index("by_project", ["projectId", "requestedAt"])
    .index("by_status", ["status"]),

  projectSecrets: defineTable({
    projectId: v.id("projects"),
    keyName: v.string(),
    encryptedValue: v.string(),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_project", ["projectId", "updatedAt"])
    .index("by_project_key", ["projectId", "keyName"]),

  agentSecretPolicies: defineTable({
    projectId: v.id("projects"),
    agentRole: v.string(),
    allowedSecretNames: v.array(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_project", ["projectId", "updatedAt"])
    .index("by_project_role", ["projectId", "agentRole"]),

  runnerEvents: defineTable({
    agentSessionId: v.id("agentSessions"),
    eventType: v.string(),
    normalizedPayload: v.any(),
    rawPayload: v.optional(v.any()),
    debugVisibility: v.optional(v.string()),
    createdAt: v.number(),
  })
    .index("by_session", ["agentSessionId", "createdAt"]),

  devices: defineTable({
    deviceId: v.string(),
    label: v.optional(v.string()),
    hostname: v.optional(v.string()),
    platform: v.optional(v.string()),
    createdAt: v.number(),
    lastSeenAt: v.number(),
  }).index("by_device_id", ["deviceId"]),

  hydrationArtifacts: defineTable({
    projectId: v.id("projects"),
    deviceId: v.string(),
    commitSha: v.string(),
    manifestFingerprint: v.string(),
    pipelineSlug: v.string(),
    hydrationMode: v.string(),
    ontologyArtifactPath: v.optional(v.string()),
    duckdbArtifactPath: v.optional(v.string()),
    status: v.string(),
    createdAt: v.number(),
    lastValidatedAt: v.optional(v.number()),
  })
    .index("by_project", ["projectId", "createdAt"])
    .index("by_device", ["deviceId", "createdAt"])
    .index("by_project_device_pipeline", ["projectId", "deviceId", "pipelineSlug"]),

  artifactIndex: defineTable({
    projectId: v.id("projects"),
    path: v.string(),
    artifactType: v.string(),
    title: v.optional(v.string()),
    description: v.optional(v.string()),
    commitSha: v.optional(v.string()),
    createdAt: v.number(),
  })
    .index("by_project", ["projectId", "createdAt"])
    .index("by_project_path", ["projectId", "path"]),
});
