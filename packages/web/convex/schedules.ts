import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const list = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db.query("scheduledPipelines").collect();
  },
});

export const listByProject = query({
  args: { projectSlug: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("scheduledPipelines")
      .withIndex("by_project", (q) => q.eq("projectSlug", args.projectSlug))
      .collect();
  },
});

export const listActive = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("scheduledPipelines")
      .withIndex("by_status", (q) => q.eq("status", "active"))
      .filter((q) => q.eq(q.field("enabled"), true))
      .collect();
  },
});

export const get = query({
  args: { id: v.id("scheduledPipelines") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.id);
  },
});

export const create = mutation({
  args: {
    projectSlug: v.string(),
    pipelineSlug: v.string(),
    cron: v.optional(v.string()),
    frequency: v.optional(v.string()),
    windowEndsAt: v.optional(v.number()),
    enabled: v.boolean(),
    status: v.string(),
    nextRunAt: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return await ctx.db.insert("scheduledPipelines", {
      ...args,
      createdAt: now,
      updatedAt: now,
    });
  },
});

export const update = mutation({
  args: {
    id: v.id("scheduledPipelines"),
    cron: v.optional(v.string()),
    frequency: v.optional(v.string()),
    windowEndsAt: v.optional(v.number()),
    enabled: v.optional(v.boolean()),
    status: v.optional(v.string()),
    lastRunAt: v.optional(v.number()),
    lastJobId: v.optional(v.string()),
    nextRunAt: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const { id, ...updates } = args;
    const now = Date.now();

    // Remove undefined values
    const cleanUpdates = Object.fromEntries(
      Object.entries(updates).filter(([_, v]) => v !== undefined)
    );

    await ctx.db.patch(id, {
      ...cleanUpdates,
      updatedAt: now,
    });
    return await ctx.db.get(id);
  },
});

export const pause = mutation({
  args: { id: v.id("scheduledPipelines") },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      enabled: false,
      status: "paused",
      updatedAt: Date.now(),
    });
    return await ctx.db.get(args.id);
  },
});

export const resume = mutation({
  args: { id: v.id("scheduledPipelines") },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      enabled: true,
      status: "active",
      updatedAt: Date.now(),
    });
    return await ctx.db.get(args.id);
  },
});

export const remove = mutation({
  args: { id: v.id("scheduledPipelines") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
  },
});
