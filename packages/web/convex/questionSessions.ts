import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const blockValidator = v.object({
  kind: v.string(),
  text: v.optional(v.string()),
  name: v.optional(v.string()),
  result: v.optional(v.any()),
  explanation: v.optional(v.string()),
  missing: v.optional(v.string()),
  sources: v.optional(v.array(v.string())),
});

export const save = mutation({
  args: {
    projectSlug: v.optional(v.string()),
    question: v.string(),
    blocks: v.array(blockValidator),
  },
  handler: async (ctx, { projectSlug, question, blocks }) => {
    let projectId = undefined;
    if (projectSlug) {
      const p = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", projectSlug)).first();
      projectId = p?._id;
    }
    return await ctx.db.insert("questionSessions", {
      projectId,
      question,
      blocks,
      createdAt: Date.now(),
    });
  },
});

export const list = query({
  args: { projectSlug: v.optional(v.string()), limit: v.optional(v.number()) },
  handler: async (ctx, { projectSlug, limit = 50 }) => {
    if (projectSlug) {
      const p = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", projectSlug)).first();
      if (!p) return [];
      return await ctx.db
        .query("questionSessions")
        .withIndex("by_project", q => q.eq("projectId", p._id))
        .order("desc")
        .take(limit);
    }
    return await ctx.db
      .query("questionSessions")
      .withIndex("by_created")
      .order("desc")
      .take(limit);
  },
});

export const remove = mutation({
  args: { id: v.id("questionSessions") },
  handler: async (ctx, { id }) => {
    await ctx.db.delete(id);
  },
});
