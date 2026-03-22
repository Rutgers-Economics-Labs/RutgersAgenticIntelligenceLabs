import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

function matchesQuery(entry: {
  sourceId: string;
  name: string;
  description: string;
  geography: string;
  tags: string[];
}, queryText: string) {
  const needle = queryText.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [
    entry.sourceId,
    entry.name,
    entry.description,
    entry.geography,
    ...entry.tags,
  ].join(" ").toLowerCase();
  return haystack.includes(needle);
}

export const list = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit }) => {
    const items = await ctx.db.query("dataSourceRegistry").collect();
    const sorted = items.sort((a, b) => b.updatedAt - a.updatedAt);
    return sorted.slice(0, limit ?? 100);
  },
});

export const search = query({
  args: {
    query: v.optional(v.string()),
    provider: v.optional(v.string()),
    geography: v.optional(v.string()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, { query: queryText, provider, geography, limit }) => {
    let items = provider
      ? await ctx.db.query("dataSourceRegistry").withIndex("by_provider", (q) => q.eq("provider", provider)).collect()
      : await ctx.db.query("dataSourceRegistry").collect();

    if (geography) {
      items = items.filter((item) => item.geography === geography);
    }
    if (queryText) {
      items = items.filter((item) => matchesQuery(item, queryText));
    }

    const sorted = items.sort((a, b) => {
      const aName = a.name.toLowerCase();
      const bName = b.name.toLowerCase();
      if (queryText) {
        const q = queryText.toLowerCase();
        const aStarts = Number(aName.startsWith(q));
        const bStarts = Number(bName.startsWith(q));
        if (aStarts !== bStarts) return bStarts - aStarts;
      }
      return aName.localeCompare(bName);
    });

    return sorted.slice(0, limit ?? 20);
  },
});

export const get = query({
  args: { provider: v.string(), sourceId: v.string() },
  handler: async (ctx, { provider, sourceId }) => {
    return await ctx.db
      .query("dataSourceRegistry")
      .withIndex("by_provider_source", (q) => q.eq("provider", provider).eq("sourceId", sourceId))
      .first();
  },
});

export const create = mutation({
  args: {
    provider: v.string(),
    sourceId: v.string(),
    name: v.string(),
    description: v.string(),
    unit: v.string(),
    frequency: v.string(),
    geography: v.string(),
    tags: v.array(v.string()),
    exampleYaml: v.string(),
    updatedAt: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const existing = await ctx.db
      .query("dataSourceRegistry")
      .withIndex("by_provider_source", (q) => q.eq("provider", args.provider).eq("sourceId", args.sourceId))
      .first();

    const payload = {
      ...args,
      updatedAt: args.updatedAt ?? now,
      createdAt: existing?.createdAt ?? now,
    };

    if (existing) {
      await ctx.db.patch(existing._id, payload);
      return existing._id;
    }

    return await ctx.db.insert("dataSourceRegistry", payload);
  },
});
