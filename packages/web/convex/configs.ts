import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// ── API configs ──────────────────────────────────────────────────────────────

export const listApis = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db.query("apiConfigs").collect();
  },
});

export const getApi = query({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) => {
    return await ctx.db.query("apiConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
  },
});

export const createApi = mutation({
  args: {
    name: v.string(),
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    sourceType: v.string(),
    isPublic: v.boolean(),
    tags: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return await ctx.db.insert("apiConfigs", { ...args, createdAt: now, updatedAt: now });
  },
});

export const updateApi = mutation({
  args: {
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    name: v.string(),
    isPublic: v.boolean(),
    tags: v.array(v.string()),
  },
  handler: async (ctx, { slug, ...fields }) => {
    const doc = await ctx.db.query("apiConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (!doc) throw new Error(`API config '${slug}' not found`);
    await ctx.db.patch(doc._id, { ...fields, updatedAt: Date.now() });
    return doc._id;
  },
});

export const deleteApi = mutation({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) => {
    const doc = await ctx.db.query("apiConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (doc) await ctx.db.delete(doc._id);
  },
});

export const upsertPipeline = mutation({
  args: {
    slug: v.string(),
    content: v.string(),
    source: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("pipelineConfigs").withIndex("by_slug", (q) => q.eq("slug", args.slug)).first();
    const now = Date.now();
    if (existing) {
      await ctx.db.patch(existing._id, { content: args.content, updatedAt: now });
      return existing._id;
    } else {
      return await ctx.db.insert("pipelineConfigs", {
        name: args.slug,
        slug: args.slug,
        content: args.content,
        parsedSpec: {},
        referencedApiSlugs: [],
        isPublic: false,
        tags: [],
        createdAt: now,
        updatedAt: now,
      });
    }
  },
});

export const upsertApi = mutation({
  args: {
    slug: v.string(),
    content: v.string(),
    source: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("apiConfigs").withIndex("by_slug", (q) => q.eq("slug", args.slug)).first();
    const now = Date.now();
    if (existing) {
      await ctx.db.patch(existing._id, { content: args.content, updatedAt: now });
      return existing._id;
    } else {
      return await ctx.db.insert("apiConfigs", {
        name: args.slug,
        slug: args.slug,
        content: args.content,
        parsedSpec: {},
        sourceType: args.source || "unknown",
        isPublic: false,
        tags: [],
        createdAt: now,
        updatedAt: now,
      });
    }
  },
});

// ── Ontology configs ─────────────────────────────────────────────────────────

export const listOntologies = query({
  args: {},
  handler: async (ctx) => ctx.db.query("ontologyConfigs").collect(),
});

export const getOntology = query({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) =>
    ctx.db.query("ontologyConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first(),
});

export const createOntology = mutation({
  args: {
    name: v.string(),
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    ontologyUri: v.string(),
    isPublic: v.boolean(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("ontologyConfigs", { ...args, createdAt: now, updatedAt: now });
  },
});

export const updateOntology = mutation({
  args: {
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    name: v.string(),
    isPublic: v.boolean(),
  },
  handler: async (ctx, { slug, ...fields }) => {
    const doc = await ctx.db.query("ontologyConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (!doc) throw new Error(`Ontology config '${slug}' not found`);
    await ctx.db.patch(doc._id, { ...fields, updatedAt: Date.now() });
    return doc._id;
  },
});

export const deleteOntology = mutation({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) => {
    const doc = await ctx.db.query("ontologyConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (doc) await ctx.db.delete(doc._id);
  },
});

export const upsertOntology = mutation({
  args: {
    slug: v.string(),
    content: v.string(),
    source: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("ontologyConfigs").withIndex("by_slug", (q) => q.eq("slug", args.slug)).first();
    const now = Date.now();
    if (existing) {
      await ctx.db.patch(existing._id, { content: args.content, updatedAt: now });
      return existing._id;
    } else {
      return await ctx.db.insert("ontologyConfigs", {
        name: args.slug,
        slug: args.slug,
        content: args.content,
        parsedSpec: {},
        ontologyUri: `https://rail.rutgers.edu/ontology/${args.slug}`,
        isPublic: false,
        createdAt: now,
        updatedAt: now,
      });
    }
  },
});

// ── Pipeline configs ─────────────────────────────────────────────────────────

export const listPipelines = query({
  args: {},
  handler: async (ctx) => ctx.db.query("pipelineConfigs").collect(),
});

export const getPipeline = query({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) =>
    ctx.db.query("pipelineConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first(),
});

export const createPipeline = mutation({
  args: {
    name: v.string(),
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    referencedApiSlugs: v.array(v.string()),
    isPublic: v.boolean(),
    tags: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("pipelineConfigs", { ...args, createdAt: now, updatedAt: now });
  },
});

export const updatePipeline = mutation({
  args: {
    slug: v.string(),
    content: v.string(),
    parsedSpec: v.any(),
    name: v.string(),
    isPublic: v.boolean(),
    tags: v.array(v.string()),
    referencedApiSlugs: v.array(v.string()),
  },
  handler: async (ctx, { slug, ...fields }) => {
    const doc = await ctx.db.query("pipelineConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (!doc) throw new Error(`Pipeline config '${slug}' not found`);
    await ctx.db.patch(doc._id, { ...fields, updatedAt: Date.now() });
    return doc._id;
  },
});

export const deletePipeline = mutation({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) => {
    const doc = await ctx.db.query("pipelineConfigs").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (doc) await ctx.db.delete(doc._id);
  },
});
