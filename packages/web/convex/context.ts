import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const create = mutation({
  args: {
    projectId: v.optional(v.id("projects")),
    name: v.string(),
    type: v.union(v.literal("pdf"), v.literal("text"), v.literal("url"), v.literal("docx")),
    content: v.string(),
    url: v.optional(v.string()),
    fileSize: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("contextDocuments", { ...args, createdAt: now, updatedAt: now });
  },
});

export const remove = mutation({
  args: { id: v.id("contextDocuments") },
  handler: async (ctx, { id }) => ctx.db.delete(id),
});

export const list = query({
  args: { projectId: v.optional(v.id("projects")) },
  handler: async (ctx, { projectId }) => {
    // Return project-specific + global docs
    const global = await ctx.db
      .query("contextDocuments")
      .withIndex("by_project", (q) => q.eq("projectId", undefined))
      .order("desc")
      .collect();
    if (!projectId) return global;
    const scoped = await ctx.db
      .query("contextDocuments")
      .withIndex("by_project", (q) => q.eq("projectId", projectId))
      .order("desc")
      .collect();
    return [...scoped, ...global];
  },
});

export const get = query({
  args: { id: v.id("contextDocuments") },
  handler: async (ctx, { id }) => ctx.db.get(id),
});
