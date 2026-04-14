import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByProject = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, { projectId }) => {
    return ctx.db.query("agentSecretPolicies").withIndex("by_project", (q) => q.eq("projectId", projectId)).order("desc").collect();
  },
});

export const getByRole = query({
  args: { projectId: v.id("projects"), agentRole: v.string() },
  handler: async (ctx, { projectId, agentRole }) =>
    ctx.db
      .query("agentSecretPolicies")
      .withIndex("by_project_role", (q) => q.eq("projectId", projectId).eq("agentRole", agentRole))
      .first(),
});

export const upsert = mutation({
  args: {
    projectId: v.id("projects"),
    agentRole: v.string(),
    allowedSecretNames: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("agentSecretPolicies")
      .withIndex("by_project_role", (q) => q.eq("projectId", args.projectId).eq("agentRole", args.agentRole))
      .first();
    const now = Date.now();
    if (existing) {
      await ctx.db.patch(existing._id, { allowedSecretNames: args.allowedSecretNames, updatedAt: now });
      return existing._id;
    }
    return ctx.db.insert("agentSecretPolicies", { ...args, createdAt: now, updatedAt: now });
  },
});

export const deleteByRole = mutation({
  args: { projectId: v.id("projects"), agentRole: v.string() },
  handler: async (ctx, { projectId, agentRole }) => {
    const existing = await ctx.db
      .query("agentSecretPolicies")
      .withIndex("by_project_role", (q) => q.eq("projectId", projectId).eq("agentRole", agentRole))
      .first();
    if (existing) await ctx.db.delete(existing._id);
  },
});
