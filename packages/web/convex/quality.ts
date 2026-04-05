import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const saveSnapshot = mutation({
  args: {
    projectSlug: v.optional(v.string()),
    label: v.string(),
    tables: v.any(),
    createdAt: v.number(),
  },
  handler: async (ctx, args) => {
    let projectId = undefined;
    if (args.projectSlug) {
      const p = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", args.projectSlug!)).first();
      projectId = p?._id;
    }
    const { projectSlug, ...rest } = args;
    return await ctx.db.insert("ontologySnapshots", { ...rest, projectId });
  },
});

export const listSnapshots = query({
  args: {
    projectSlug: v.optional(v.string()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, { projectSlug, limit = 10 }) => {
    if (projectSlug) {
      const p = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", projectSlug)).first();
      if (!p) return [];
      return await ctx.db
        .query("ontologySnapshots")
        .withIndex("by_project", q => q.eq("projectId", p._id))
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
