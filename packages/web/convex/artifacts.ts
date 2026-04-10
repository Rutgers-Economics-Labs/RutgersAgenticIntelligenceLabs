import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const create = mutation({
  args: {
    rev: v.string(),
    projectId: v.string(),
    s3_path: v.string(),
    timestamp: v.number(),
  },
  handler: async (ctx, args) => {
    return ctx.db.insert("artifactRevs", args);
  },
});

export const getByRev = query({
  args: { rev: v.string() },
  handler: async (ctx, { rev }) =>
    ctx.db.query("artifactRevs").withIndex("by_rev", (q) => q.eq("rev", rev)).first(),
});
