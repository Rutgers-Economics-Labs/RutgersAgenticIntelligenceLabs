import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const create = mutation({
  args: {
    projectSlug: v.optional(v.string()),
    name: v.string(),
    type: v.union(v.literal("pdf"), v.literal("text"), v.literal("url"), v.literal("docx")),
    content: v.string(),
    url: v.optional(v.string()),
    fileSize: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    let projectId = undefined;
    if (args.projectSlug) {
      const p = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", args.projectSlug!)).first();
      projectId = p?._id;
    }
    const { projectSlug, ...rest } = args;
    return ctx.db.insert("contextDocuments", { ...rest, projectId, createdAt: now, updatedAt: now });
  },
});

export const remove = mutation({
  args: { id: v.id("contextDocuments") },
  handler: async (ctx, { id }) => ctx.db.delete(id),
});

export const list = query({
  args: { projectSlug: v.optional(v.string()) },
  handler: async (ctx, { projectSlug }) => {
    // Return project-specific + global docs
    const global = await ctx.db
      .query("contextDocuments")
      .withIndex("by_project", (q) => q.eq("projectId", undefined))
      .order("desc")
      .collect();
    if (!projectSlug) return global;
    const p = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", projectSlug)).first();
    if (!p) return global;
    const scoped = await ctx.db
      .query("contextDocuments")
      .withIndex("by_project", (q) => q.eq("projectId", p._id))
      .order("desc")
      .collect();
    return [...scoped, ...global];
  },
});

export const get = query({
  args: { id: v.id("contextDocuments") },
  handler: async (ctx, { id }) => ctx.db.get(id),
});
