import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const saveSnapshot = mutation({
  args: {
    projectId: v.optional(v.id("projects")),
    label: v.string(),
    tables: v.any(),
    createdAt: v.number(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("ontologySnapshots", args);
  },
});

export const listSnapshots = query({
  args: {
    projectId: v.optional(v.id("projects")),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, { projectId, limit = 10 }) => {
    if (projectId) {
      return await ctx.db
        .query("ontologySnapshots")
        .withIndex("by_project", q => q.eq("projectId", projectId))
        .order("desc")
        .take(limit);
    }
    return await ctx.db
      .query("ontologySnapshots")
      .withIndex("by_created")
      .order("desc")
      .take(limit);
  },
});

export const remove = mutation({
  args: { id: v.id("ontologySnapshots") },
  handler: async (ctx, { id }) => {
    await ctx.db.delete(id);
  },
});
