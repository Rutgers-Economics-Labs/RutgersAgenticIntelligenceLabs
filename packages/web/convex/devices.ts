import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const getByDeviceId = query({
  args: { deviceId: v.string() },
  handler: async (ctx, { deviceId }) => {
    return ctx.db.query("devices").withIndex("by_device_id", (q) => q.eq("deviceId", deviceId)).first();
  },
});

export const heartbeat = mutation({
  args: {
    deviceId: v.string(),
    label: v.optional(v.string()),
    hostname: v.optional(v.string()),
    platform: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("devices").withIndex("by_device_id", (q) => q.eq("deviceId", args.deviceId)).first();
    const now = Date.now();
    if (existing) {
      await ctx.db.patch(existing._id, { ...args, lastSeenAt: now });
      return existing._id;
    }
    return ctx.db.insert("devices", { ...args, createdAt: now, lastSeenAt: now });
  },
});
