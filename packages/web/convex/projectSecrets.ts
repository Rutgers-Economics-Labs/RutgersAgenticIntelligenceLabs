import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByProject = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, { projectId }) => {
    return ctx.db.query("projectSecrets").withIndex("by_project", (q) => q.eq("projectId", projectId)).order("desc").collect();
  },
});

export const upsert = mutation({
  args: {
    projectId: v.id("projects"),
    keyName: v.string(),
    encryptedValue: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("projectSecrets")
      .withIndex("by_project_key", (q) => q.eq("projectId", args.projectId).eq("keyName", args.keyName))
      .first();
    const now = Date.now();
    if (existing) {
      await ctx.db.patch(existing._id, { encryptedValue: args.encryptedValue, updatedAt: now });
      return existing._id;
    }
    return ctx.db.insert("projectSecrets", { ...args, createdAt: now, updatedAt: now });
  },
});

export const deleteByKey = mutation({
  args: { projectId: v.id("projects"), keyName: v.string() },
  handler: async (ctx, { projectId, keyName }) => {
    const existing = await ctx.db
      .query("projectSecrets")
      .withIndex("by_project_key", (q) => q.eq("projectId", projectId).eq("keyName", keyName))
      .first();
    if (existing) await ctx.db.delete(existing._id);
  },
});
