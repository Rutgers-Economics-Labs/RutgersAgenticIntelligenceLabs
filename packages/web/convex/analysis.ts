import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const saveScript = mutation({
  args: {
    id: v.optional(v.id("analysisScripts")),
    projectId: v.id("projects"),
    name: v.string(),
    code: v.string(),
    description: v.optional(v.string()),
    lastJobId: v.optional(v.id("executionJobs")),
  },
  handler: async (ctx, { id, ...fields }) => {
    const now = Date.now();
    if (id) {
      await ctx.db.patch(id, { ...fields, updatedAt: now });
      return id;
    } else {
      return await ctx.db.insert("analysisScripts", {
        ...fields,
        createdAt: now,
        updatedAt: now,
      });
    }
  },
});

export const getScript = query({
  args: { id: v.id("analysisScripts") },
  handler: async (ctx, { id }) => ctx.db.get(id),
});

export const listScripts = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, { projectId }) => {
    return ctx.db.query("analysisScripts")
      .withIndex("by_project", (q) => q.eq("projectId", projectId))
      .order("desc")
      .collect();
  },
});

export const deleteScript = mutation({
  args: { id: v.id("analysisScripts") },
  handler: async (ctx, { id }) => {
    await ctx.db.delete(id);
  },
});
