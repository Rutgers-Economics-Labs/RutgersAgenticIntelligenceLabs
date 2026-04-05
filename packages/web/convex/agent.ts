import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listSessions = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit = 20 }) => {
    return await ctx.db
      .query("agentSessions")
      .withIndex("by_created")
      .order("desc")
      .take(limit);
  },
});

export const listByProject = query({
  args: { projectSlug: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, { projectSlug, limit = 20 }) => {
    return await ctx.db
      .query("agentSessions")
      .withIndex("by_project", q => q.eq("projectSlug", projectSlug))
      .order("desc")
      .take(limit);
  },
});

export const getSession = query({
  args: { sessionId: v.id("agentSessions") },
  handler: async (ctx, { sessionId }) => {
    return await ctx.db.get(sessionId);
  },
});

export const createSession = mutation({
  args: {
    title: v.string(),
    model: v.string(),
    projectSlug: v.optional(v.string()),
  },
  handler: async (ctx, { title, model, projectSlug }) => {
    const now = Date.now();
    const sessionId = await ctx.db.insert("agentSessions", {
      title,
      model,
      projectSlug,
      messages: [],
      createdAt: now,
      updatedAt: now,
    });
    return { sessionId };
  },
});

export const appendMessages = mutation({
  args: {
    sessionId: v.id("agentSessions"),
    messages: v.array(v.object({
      role: v.union(v.literal("user"), v.literal("assistant"), v.literal("tool")),
      content: v.optional(v.string()),
      tool_calls: v.optional(v.any()),
      tool_call_id: v.optional(v.string()),
    })),
  },
  handler: async (ctx, { sessionId, messages }) => {
    const session = await ctx.db.get(sessionId);
    if (!session) throw new Error("Session not found");
    await ctx.db.patch(sessionId, {
      messages: [...session.messages, ...messages],
      updatedAt: Date.now(),
    });
  },
});

export const updateTitle = mutation({
  args: { sessionId: v.id("agentSessions"), title: v.string() },
  handler: async (ctx, { sessionId, title }) => {
    await ctx.db.patch(sessionId, { title, updatedAt: Date.now() });
  },
});

export const deleteSession = mutation({
  args: { sessionId: v.id("agentSessions") },
  handler: async (ctx, { sessionId }) => {
    await ctx.db.delete(sessionId);
  },
});
