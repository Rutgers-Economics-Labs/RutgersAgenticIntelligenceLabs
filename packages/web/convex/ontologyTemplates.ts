import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const list = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db.query("ontologyTemplates").order("desc").collect();
  },
});

export const listByTag = query({
  args: { tags: v.array(v.string()) },
  handler: async (ctx, args) => {
    const templates = await ctx.db.query("ontologyTemplates").order("desc").collect();
    if (args.tags.length === 0) return templates;
    return templates.filter((t) => args.tags.some((tag) => t.tags.includes(tag)));
  },
});

export const getBySlug = query({
  args: { slug: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("ontologyTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .first();
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
      .query("ontologyTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .first();
    if (existing) {
      throw new Error(`Ontology template with slug ${args.slug} already exists`);
    }

    const now = Date.now();
    const id = await ctx.db.insert("ontologyTemplates", {
      ...args,
      createdAt: now,
      updatedAt: now,
    });
    return id;
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
      .query("ontologyTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .first();
    if (!existing) {
      throw new Error(`Ontology template with slug ${args.slug} not found`);
    }

    const patch: any = { updatedAt: Date.now() };
    if (args.name !== undefined) patch.name = args.name;
    if (args.description !== undefined) patch.description = args.description;
    if (args.version !== undefined) patch.version = args.version;
    if (args.tags !== undefined) patch.tags = args.tags;
    if (args.content !== undefined) patch.content = args.content;

    await ctx.db.patch(existing._id, patch);
    return existing._id;
  },
});

export const remove = mutation({
  args: { slug: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("ontologyTemplates")
      .withIndex("by_slug", (q) => q.eq("slug", args.slug))
      .first();
    if (!existing) {
      throw new Error(`Ontology template with slug ${args.slug} not found`);
    }

    await ctx.db.delete(existing._id);
    return true;
  },
});
