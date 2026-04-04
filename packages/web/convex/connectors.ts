import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const list = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db.query("connectorTemplates").order("desc").collect();
  },
});

export const listByTag = query({
  args: { tag: v.string() },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("connectorTemplates").order("desc").collect();
    return all.filter((c) => c.tags?.includes(args.tag));
  },
});

export const getBySlug = query({
  args: { slug: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("connectorTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .unique();
  },
});

export const create = mutation({
  args: {
    slug: v.string(),
    name: v.string(),
    description: v.string(),
    version: v.string(),
    tags: v.array(v.string()),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("connectorTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .unique();
    if (existing) {
      throw new Error(`Connector template with slug '${args.slug}' already exists.`);
    }

    const now = Date.now();
    return await ctx.db.insert("connectorTemplates", {
      ...args,
      usageCount: 0,
      createdAt: now,
      updatedAt: now,
    });
  },
});

export const update = mutation({
  args: {
    slug: v.string(),
    name: v.optional(v.string()),
    description: v.optional(v.string()),
    version: v.optional(v.string()),
    tags: v.optional(v.array(v.string())),
    content: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("connectorTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .unique();
    if (!existing) {
      throw new Error(`Connector template '${args.slug}' not found.`);
    }

    const { slug, ...updates } = args;
    await ctx.db.patch(existing._id, {
      ...updates,
      updatedAt: Date.now(),
    });

    return existing._id;
  },
});

export const remove = mutation({
  args: { slug: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("connectorTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .unique();
    if (!existing) {
      throw new Error(`Connector template '${args.slug}' not found.`);
    }

    await ctx.db.delete(existing._id);
    return { success: true };
  },
});

export const incrementUsage = mutation({
  args: { slug: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("connectorTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .unique();
    if (existing) {
      await ctx.db.patch(existing._id, {
        usageCount: (existing.usageCount || 0) + 1,
      });
    }
  },
});
