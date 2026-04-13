import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByBoard = query({
  args: { boardId: v.id("taskBoards") },
  handler: async (ctx, { boardId }) => {
    return ctx.db.query("tasks").withIndex("by_board", (q) => q.eq("boardId", boardId)).order("desc").collect();
  },
});

export const create = mutation({
  args: {
    boardId: v.id("taskBoards"),
    projectId: v.id("projects"),
    sessionId: v.optional(v.string()),
    title: v.string(),
    description: v.string(),
    status: v.string(),
    priority: v.optional(v.string()),
    agentRole: v.string(),
    runner: v.optional(v.string()),
    repoPaths: v.array(v.string()),
    acceptanceCriteria: v.array(v.string()),
    dependsOnTaskIds: v.array(v.id("tasks")),
    approvalState: v.optional(v.string()),
    gitSnapshotPath: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("tasks", { ...args, createdAt: now, updatedAt: now });
  },
});

export const update = mutation({
  args: {
    taskId: v.id("tasks"),
    title: v.optional(v.string()),
    description: v.optional(v.string()),
    status: v.optional(v.string()),
    priority: v.optional(v.string()),
    runner: v.optional(v.string()),
    repoPaths: v.optional(v.array(v.string())),
    acceptanceCriteria: v.optional(v.array(v.string())),
    approvalState: v.optional(v.string()),
    gitSnapshotPath: v.optional(v.string()),
  },
  handler: async (ctx, { taskId, ...fields }) => {
    const patch = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined));
    await ctx.db.patch(taskId, { ...patch, updatedAt: Date.now() });
  },
});
