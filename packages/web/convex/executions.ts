import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const create = mutation({
  args: {
    projectId: v.optional(v.id("projects")),
    workspaceId: v.optional(v.id("workspaces")),
    cellId: v.optional(v.string()),
    hydrationId: v.optional(v.id("hydrationJobs")),
    type: v.union(v.literal("sql"), v.literal("code")),
    input: v.string(),
    createdAt: v.number(),
  },
  handler: async (ctx, args) => {
    const jobId = await ctx.db.insert("executionJobs", {
      ...args,
      status: "queued",
    });

    // Update workspace cell if applicable
    if (args.workspaceId && args.cellId) {
      const workspace = await ctx.db.get(args.workspaceId);
      if (workspace) {
        const cells = workspace.cells.map(c => 
          c.id === args.cellId ? { ...c, lastJobId: jobId } : c
        );
        await ctx.db.patch(args.workspaceId, { cells });
      }
    }

    return { jobId };
  },
});

export const updateStatus = mutation({
  args: {
    jobId: v.id("executionJobs"),
    status: v.union(
      v.literal("queued"),
      v.literal("running"),
      v.literal("success"),
      v.literal("failed"),
      v.literal("cancelled"),
    ),
    startedAt: v.optional(v.number()),
    finishedAt: v.optional(v.number()),
    result: v.optional(v.any()),
    errorMessage: v.optional(v.string()),
  },
  handler: async (ctx, { jobId, ...fields }) => {
    await ctx.db.patch(jobId, fields);
  },
});

export const get = query({
  args: { jobId: v.string() },
  handler: async (ctx, { jobId }) => {
    try {
      const doc = await ctx.db.get(jobId as any);
      // Ensure we only return it if it looks like an execution job
      // to avoid collisions with hydration job IDs.
      if (doc && ("type" in doc)) {
        return doc;
      }
      return null;
    } catch (e) {
      return null;
    }
  },
});

export const listByWorkspace = query({
  args: { workspaceId: v.id("workspaces"), cellId: v.string() },
  handler: async (ctx, { workspaceId, cellId }) => {
    return ctx.db.query("executionJobs")
      .withIndex("by_workspace_cell", (q) => q.eq("workspaceId", workspaceId).eq("cellId", cellId))
      .order("desc")
      .collect();
  },
});

export const listByProject = query({
  args: { projectId: v.id("projects"), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, limit }) => {
    return ctx.db.query("executionJobs")
      .withIndex("by_project", (q) => q.eq("projectId", projectId))
      .order("desc")
      .take(limit ?? 50);
  },
});

export const list = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit }) => {
    return await ctx.db.query("executionJobs")
      .withIndex("by_created")
      .order("desc")
      .take(limit ?? 100);
  },
});
