import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByScript = query({
  args: { scriptId: v.id("projectScripts"), limit: v.optional(v.number()) },
  handler: async (ctx, { scriptId, limit = 20 }) =>
    ctx.db
      .query("scriptRuns")
      .withIndex("by_script_created", (q) => q.eq("scriptId", scriptId))
      .order("desc")
      .take(limit),
});

export const create = mutation({
  args: {
    scriptId: v.id("projectScripts"),
    projectId: v.id("projects"),
    codeSnapshot: v.string(),
  },
  handler: async (ctx, args) =>
    ctx.db.insert("scriptRuns", {
      ...args,
      status: "running",
      figureCount: 0,
      figureStorageKeys: [],
      createdAt: Date.now(),
    }),
});

export const complete = mutation({
  args: {
    runId: v.id("scriptRuns"),
    status: v.union(v.literal("success"), v.literal("failed")),
    stdout: v.optional(v.string()),
    error: v.optional(v.string()),
    figureCount: v.number(),
    figureStorageKeys: v.array(v.string()),
    dfSummary: v.optional(v.any()),
    finishedAt: v.number(),
  },
  handler: async (ctx, { runId, ...fields }) => {
    await ctx.db.patch(runId, fields);
  },
});

export const get = query({
  args: { runId: v.id("scriptRuns") },
  handler: async (ctx, { runId }) => ctx.db.get(runId),
});
