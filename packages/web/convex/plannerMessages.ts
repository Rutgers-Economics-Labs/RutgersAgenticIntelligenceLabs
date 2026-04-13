import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByProjectThread = query({
  args: { projectId: v.id("projects"), threadId: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, threadId, limit = 200 }) => {
    return ctx.db
      .query("plannerMessages")
      .withIndex("by_project_thread", (q) => q.eq("projectId", projectId).eq("threadId", threadId))
      .order("desc")
      .take(limit);
  },
});

export const append = mutation({
  args: {
    projectId: v.id("projects"),
    sessionId: v.optional(v.string()),
    threadId: v.string(),
    role: v.union(v.literal("user"), v.literal("assistant"), v.literal("system")),
    content: v.string(),
    messageType: v.string(),
  },
  handler: async (ctx, args) => {
    return ctx.db.insert("plannerMessages", { ...args, createdAt: Date.now() });
  },
});
