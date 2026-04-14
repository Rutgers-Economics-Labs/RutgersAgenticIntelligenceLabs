import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const listByTask = query({
  args: { taskId: v.id("tasks"), limit: v.optional(v.number()) },
  handler: async (ctx, { taskId, limit = 200 }) => {
    return ctx.db.query("taskEvents").withIndex("by_task", (q) => q.eq("taskId", taskId)).order("desc").take(limit);
  },
});

export const append = mutation({
  args: {
    taskId: v.id("tasks"),
    eventType: v.string(),
    payload: v.any(),
  },
  handler: async (ctx, args) => {
    return ctx.db.insert("taskEvents", { ...args, createdAt: Date.now() });
  },
});

/**
 * Record a normalized verification result (passed or failed) for a task.
 * The payload shape mirrors VerificationSummary.as_task_event_payload() from
 * the Python completion gate.
 */
export const recordVerification = mutation({
  args: {
    taskId: v.id("tasks"),
    passed: v.boolean(),
    role: v.string(),
    failures: v.array(v.object({
      hook: v.string(),
      check: v.string(),
      message: v.string(),
    })),
    hookResults: v.optional(v.any()),
  },
  handler: async (ctx, { taskId, passed, role, failures, hookResults }) => {
    const eventType = passed ? "verification_passed" : "verification_failed";
    const payload = { role, passed, failures, hookResults };
    await ctx.db.insert("taskEvents", { taskId, eventType, payload, createdAt: Date.now() });

    // If verification failed, move task to blocked so the planner can review.
    if (!passed) {
      await ctx.db.patch(taskId, { status: "blocked", updatedAt: Date.now() });
    }

    return { eventType, taskId };
  },
});
