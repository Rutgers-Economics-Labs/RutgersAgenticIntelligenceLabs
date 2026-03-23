import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
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
  })
    .index("by_pipeline", ["pipelineConfigId"])
    .index("by_project", ["projectId"])
    .index("by_status", ["status"])
    .index("by_created", ["createdAt"]),

  projects: defineTable({
    name: v.string(),
    slug: v.string(),
    description: v.optional(v.string()),
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
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_slug", ["slug"])
    .index("by_status", ["status"]),

  jobLogs: defineTable({
    jobId: v.id("hydrationJobs"),
    seq: v.number(),
    level: v.union(v.literal("info"), v.literal("warn"), v.literal("error")),
    message: v.string(),
    stepName: v.optional(v.string()),
    timestamp: v.number(),
  })
    .index("by_job", ["jobId"])
    .index("by_job_seq", ["jobId", "seq"]),

  // AI agent sessions — stores conversation history
  agentSessions: defineTable({
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
  }).index("by_created", ["createdAt"]),

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
      role: v.optional(v.string()),  // "user" | "assistant" for chat cells
    })),
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index("by_created", ["createdAt"]),
});
