import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const list = query({
  args: {},
  handler: async (ctx) => ctx.db.query("projects").order("desc").collect(),
});

export const get = query({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) =>
    ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", slug)).first(),
});

export const create = mutation({
  args: {
    name: v.string(),
    slug: v.string(),
    description: v.optional(v.string()),
    approach: v.union(v.literal("data-first"), v.literal("ontology-first")),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("projects", {
      ...args,
      apiConfigSlugs: [],
      status: "draft",
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
    ontologyConfigSlug: v.optional(v.string()),
    apiConfigSlugs: v.optional(v.array(v.string())),
    pipelineConfigSlug: v.optional(v.string()),
    status: v.optional(v.union(v.literal("draft"), v.literal("ready"), v.literal("hydrated"))),
    lastJobId: v.optional(v.string()),
  },
  handler: async (ctx, { slug, ...fields }) => {
    const doc = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (!doc) throw new Error(`Project '${slug}' not found`);
    // Remove undefined values so we don't patch with undefined
    const patch = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined));
    await ctx.db.patch(doc._id, { ...patch, updatedAt: Date.now() });
    return doc._id;
  },
});

export const remove = mutation({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) => {
    const doc = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (doc) await ctx.db.delete(doc._id);
  },
});
