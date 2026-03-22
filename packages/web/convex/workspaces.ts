import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const cellValidator = v.object({
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
  role: v.optional(v.string()),
});

export const listWorkspaces = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit = 20 }) => {
    return await ctx.db
      .query("workspaces")
      .withIndex("by_created")
      .order("desc")
      .take(limit);
  },
});

export const getWorkspace = query({
  args: { workspaceId: v.string() },
  handler: async (ctx, { workspaceId }) => {
    return await ctx.db.get(workspaceId as any);
  },
});

export const createWorkspace = mutation({
  args: {
    title: v.string(),
    sessionId: v.optional(v.string()),
    pipelineSlug: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const workspaceId = await ctx.db.insert("workspaces", {
      title: args.title,
      sessionId: args.sessionId,
      pipelineSlug: args.pipelineSlug,
      cells: [],
      createdAt: now,
      updatedAt: now,
    });
    return { workspaceId };
  },
});

export const updateCells = mutation({
  args: {
    workspaceId: v.string(),
    cells: v.array(cellValidator),
  },
  handler: async (ctx, { workspaceId, cells }) => {
    await ctx.db.patch(workspaceId as any, { cells, updatedAt: Date.now() });
  },
});

export const updateTitle = mutation({
  args: { workspaceId: v.string(), title: v.string() },
  handler: async (ctx, { workspaceId, title }) => {
    await ctx.db.patch(workspaceId as any, { title, updatedAt: Date.now() });
  },
});

export const deleteWorkspace = mutation({
  args: { workspaceId: v.string() },
  handler: async (ctx, { workspaceId }) => {
    await ctx.db.delete(workspaceId as any);
  },
});
