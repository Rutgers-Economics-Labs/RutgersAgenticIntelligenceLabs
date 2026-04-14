import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const get = query({
  args: { boardId: v.id("taskBoards") },
  handler: async (ctx, { boardId }) => ctx.db.get(boardId),
});

export const listByProject = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, { projectId }) => {
    return ctx.db.query("taskBoards").withIndex("by_project", (q) => q.eq("projectId", projectId)).order("desc").collect();
  },
});

export const create = mutation({
  args: {
    projectId: v.id("projects"),
    sessionId: v.optional(v.string()),
    title: v.string(),
    status: v.string(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("taskBoards", { ...args, createdAt: now, updatedAt: now });
  },
});

export const update = mutation({
  args: {
    boardId: v.id("taskBoards"),
    title: v.optional(v.string()),
    status: v.optional(v.string()),
  },
  handler: async (ctx, { boardId, ...fields }) => {
    const patch = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined));
    await ctx.db.patch(boardId, { ...patch, updatedAt: Date.now() });
  },
});
