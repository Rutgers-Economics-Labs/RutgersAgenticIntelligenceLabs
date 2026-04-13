import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByProject = query({
  args: { projectId: v.id("projects"), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, limit = 100 }) => {
    return ctx.db.query("approvals").withIndex("by_project", (q) => q.eq("projectId", projectId)).order("desc").take(limit);
  },
});

export const create = mutation({
  args: {
    projectId: v.id("projects"),
    taskId: v.optional(v.id("tasks")),
    agentSessionId: v.optional(v.id("agentSessions")),
    approvalType: v.string(),
    status: v.string(),
    requestedByRole: v.string(),
    grantedByUserId: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("approvals", { ...args, requestedAt: now, resolvedAt: undefined });
  },
});

export const resolve = mutation({
  args: {
    approvalId: v.id("approvals"),
    status: v.string(),
    grantedByUserId: v.optional(v.string()),
  },
  handler: async (ctx, { approvalId, status, grantedByUserId }) => {
    await ctx.db.patch(approvalId, { status, grantedByUserId, resolvedAt: Date.now() });
  },
});
