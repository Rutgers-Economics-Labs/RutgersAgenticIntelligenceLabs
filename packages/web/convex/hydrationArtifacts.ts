import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByProject = query({
  args: { projectId: v.id("projects"), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, limit = 100 }) => {
    return ctx.db.query("hydrationArtifacts").withIndex("by_project", (q) => q.eq("projectId", projectId)).order("desc").take(limit);
  },
});

export const listByProjectDevicePipeline = query({
  args: {
    projectId: v.id("projects"),
    deviceId: v.string(),
    pipelineSlug: v.string(),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, { projectId, deviceId, pipelineSlug, limit = 50 }) => {
    return ctx.db
      .query("hydrationArtifacts")
      .withIndex("by_project_device_pipeline", (q) =>
        q.eq("projectId", projectId).eq("deviceId", deviceId).eq("pipelineSlug", pipelineSlug),
      )
      .order("desc")
      .take(limit);
  },
});

export const register = mutation({
  args: {
    projectId: v.id("projects"),
    deviceId: v.string(),
    commitSha: v.string(),
    manifestFingerprint: v.string(),
    pipelineSlug: v.string(),
    hydrationMode: v.string(),
    ontologyArtifactPath: v.optional(v.string()),
    duckdbArtifactPath: v.optional(v.string()),
    status: v.string(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("hydrationArtifacts", { ...args, createdAt: now, lastValidatedAt: now });
  },
});

export const markValidated = mutation({
  args: {
    artifactId: v.id("hydrationArtifacts"),
    status: v.optional(v.string()),
  },
  handler: async (ctx, { artifactId, status }) => {
    const patch: Record<string, unknown> = { lastValidatedAt: Date.now() };
    if (status !== undefined) patch.status = status;
    await ctx.db.patch(artifactId, patch);
  },
});
