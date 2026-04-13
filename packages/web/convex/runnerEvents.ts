import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listBySession = query({
  args: { agentSessionId: v.id("agentSessions"), limit: v.optional(v.number()) },
  handler: async (ctx, { agentSessionId, limit = 200 }) => {
    return ctx.db.query("runnerEvents").withIndex("by_session", (q) => q.eq("agentSessionId", agentSessionId)).order("desc").take(limit);
  },
});

export const append = mutation({
  args: {
    agentSessionId: v.id("agentSessions"),
    eventType: v.string(),
    normalizedPayload: v.any(),
    rawPayload: v.optional(v.any()),
    debugVisibility: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    return ctx.db.insert("runnerEvents", { ...args, createdAt: Date.now() });
  },
});
