import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const create = mutation({
  args: {
    jobId: v.id("hydrationJobs"),
    name: v.string(),
    artifactType: v.union(
      v.literal("text"),
      v.literal("image"),
      v.literal("model"),
      v.literal("file"),
    ),
    storageKey: v.string(),
    mimeType: v.string(),
    sizeBytes: v.number(),
    inlineContent: v.optional(v.string()),
    createdAt: v.number(),
  },
  handler: async (ctx, args) => {
    return ctx.db.insert("jobArtifacts", args);
  },
});

export const listByJob = query({
  args: { jobId: v.id("hydrationJobs") },
  handler: async (ctx, { jobId }) => {
    return ctx.db
      .query("jobArtifacts")
      .withIndex("by_job_created", (q) => q.eq("jobId", jobId))
      .order("asc")
      .collect();
  },
});
