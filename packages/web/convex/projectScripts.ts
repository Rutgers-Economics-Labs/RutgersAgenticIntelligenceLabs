import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByProject = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, { projectId }) =>
    ctx.db
      .query("projectScripts")
      .withIndex("by_project_updated", (q) => q.eq("projectId", projectId))
      .order("desc")
      .collect(),
});

export const create = mutation({
  args: {
    projectId: v.id("projects"),
    name: v.string(),
    code: v.string(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("projectScripts", { ...args, createdAt: now, updatedAt: now });
  },
});

export const update = mutation({
  args: {
    scriptId: v.id("projectScripts"),
    name: v.optional(v.string()),
    code: v.optional(v.string()),
  },
  handler: async (ctx, { scriptId, ...fields }) => {
    const patch: Record<string, unknown> = { updatedAt: Date.now() };
    if (fields.name !== undefined) patch.name = fields.name;
    if (fields.code !== undefined) patch.code = fields.code;
    await ctx.db.patch(scriptId, patch);
  },
});

export const remove = mutation({
  args: { scriptId: v.id("projectScripts") },
  handler: async (ctx, { scriptId }) => ctx.db.delete(scriptId),
});
