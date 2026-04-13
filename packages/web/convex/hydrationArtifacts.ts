import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByProject = query({
  args: { projectId: v.id("projects"), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, limit = 100 }) => {
    return ctx.db.query("hydrationArtifacts").withIndex("by_project", (q) => q.eq("projectId", projectId)).order("desc").take(limit);
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
