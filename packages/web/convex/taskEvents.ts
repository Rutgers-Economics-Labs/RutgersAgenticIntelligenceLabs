import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByTask = query({
  args: { taskId: v.id("tasks"), limit: v.optional(v.number()) },
  handler: async (ctx, { taskId, limit = 200 }) => {
    return ctx.db.query("taskEvents").withIndex("by_task", (q) => q.eq("taskId", taskId)).order("desc").take(limit);
  },
});

export const append = mutation({
  args: {
    taskId: v.id("tasks"),
    eventType: v.string(),
    payload: v.any(),
  },
  handler: async (ctx, args) => {
    return ctx.db.insert("taskEvents", { ...args, createdAt: Date.now() });
  },
});
