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

  hydrationJobs: defineTable({
    pipelineConfigId: v.id("pipelineConfigs"),
    pipelineSlug: v.string(),
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
    .index("by_status", ["status"])
    .index("by_created", ["createdAt"]),

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
});
