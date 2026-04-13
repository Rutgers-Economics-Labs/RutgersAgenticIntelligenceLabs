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

export const listByProjectId = query({
  args: { projectId: v.id("projects"), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, limit = 20 }) => {
    return await ctx.db
      .query("agentSessions")
      .withIndex("by_project_id", (q) => q.eq("projectId", projectId))
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
    projectId: v.optional(v.id("projects")),
    taskId: v.optional(v.id("tasks")),
    role: v.optional(v.string()),
    runner: v.optional(v.string()),
    externalSessionId: v.optional(v.string()),
    status: v.optional(v.string()),
    estimatedCostUsd: v.optional(v.number()),
    actualCostUsd: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const sessionId = await ctx.db.insert("agentSessions", {
      title: args.title,
      model: args.model,
      projectSlug: args.projectSlug,
      projectId: args.projectId,
      taskId: args.taskId,
      role: args.role,
      runner: args.runner,
      externalSessionId: args.externalSessionId,
      status: args.status,
      estimatedCostUsd: args.estimatedCostUsd,
      actualCostUsd: args.actualCostUsd,
      startedAt: now,
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

export const updateSessionState = mutation({
  args: {
    sessionId: v.id("agentSessions"),
    status: v.optional(v.string()),
    externalSessionId: v.optional(v.string()),
    estimatedCostUsd: v.optional(v.number()),
    actualCostUsd: v.optional(v.number()),
    endedAt: v.optional(v.number()),
  },
  handler: async (ctx, { sessionId, ...fields }) => {
    const patch = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined));
    await ctx.db.patch(sessionId, { ...patch, updatedAt: Date.now() });
  },
});

export const deleteSession = mutation({
  args: { sessionId: v.id("agentSessions") },
  handler: async (ctx, { sessionId }) => {
    await ctx.db.delete(sessionId);
  },
});
