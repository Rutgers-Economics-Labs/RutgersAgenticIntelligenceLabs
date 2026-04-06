import { mutation, query } from "./_generated/server";
import { v } from "convex/values";
import type { Id } from "./_generated/dataModel";

export const create = mutation({
  args: {
    pipelineConfigId: v.id("pipelineConfigs"),
    pipelineSlug: v.string(),
    projectSlug: v.optional(v.string()),
    status: v.literal("queued"),
    triggeredBy: v.optional(v.string()),
    createdAt: v.number(),
    stepResults: v.array(v.object({
      stepName: v.string(),
      status: v.union(v.literal("pending"), v.literal("running"), v.literal("done"), v.literal("failed")),
      rowCount: v.optional(v.number()),
      errorMessage: v.optional(v.string()),
      startedAt: v.optional(v.number()),
      finishedAt: v.optional(v.number()),
    })),
    machine: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const { projectSlug, machine, ...rest } = args;
    let projectId: Id<"projects"> | undefined;
    if (projectSlug) {
      const project = await ctx.db
        .query("projects")
        .withIndex("by_slug", (q) => q.eq("slug", projectSlug))
        .first();
      if (project) {
        projectId = project._id;
      }
    }
    const jobId = await ctx.db.insert("hydrationJobs", {
      pipelineConfigId: rest.pipelineConfigId,
      pipelineSlug: rest.pipelineSlug,
      projectId,
      ...(projectSlug ? { projectSlug } : {}),
      status: rest.status,
      triggeredBy: rest.triggeredBy,
      createdAt: rest.createdAt,
      stepResults: rest.stepResults,
      ...(machine !== undefined ? { machine } : {}),
    });
    return { jobId };
  },
});

export const updateJob = mutation({
  args: {
    jobId: v.id("hydrationJobs"),
    status: v.optional(v.union(
      v.literal("queued"), v.literal("running"),
      v.literal("success"), v.literal("failed"), v.literal("cancelled"),
    )),
    startedAt: v.optional(v.number()),
    finishedAt: v.optional(v.number()),
    errorMessage: v.optional(v.string()),
    outputOwlPath: v.optional(v.string()),
    outputDbPath: v.optional(v.string()),
  },
  handler: async (ctx, { jobId, ...fields }) => {
    const patch: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(fields)) {
      if (v !== undefined) patch[k] = v;
    }
    await ctx.db.patch(jobId, patch);
  },
});

export const updateStep = mutation({
  args: {
    jobId: v.id("hydrationJobs"),
    stepName: v.string(),
    status: v.union(v.literal("pending"), v.literal("running"), v.literal("done"), v.literal("failed")),
    rowCount: v.optional(v.number()),
    timestamp: v.number(),
  },
  handler: async (ctx, { jobId, stepName, status, rowCount, timestamp }) => {
    const job = await ctx.db.get(jobId);
    if (!job) return;
    const steps = [...job.stepResults];
    const idx = steps.findIndex((s) => s.stepName === stepName);
    const updated = {
      stepName,
      status,
      rowCount,
      startedAt: status === "running" ? timestamp : steps[idx]?.startedAt,
      finishedAt: status === "done" || status === "failed" ? timestamp : undefined,
    };
    if (idx >= 0) {
      steps[idx] = updated;
    } else {
      steps.push(updated);
    }
    await ctx.db.patch(jobId, { stepResults: steps });
  },
});

export const appendLog = mutation({
  args: {
    jobId: v.string(), // Generic ID (hydration or execution)
    seq: v.number(),
    level: v.union(v.literal("info"), v.literal("warn"), v.literal("error"), v.literal("stdout"), v.literal("stderr")),
    message: v.string(),
    stepName: v.optional(v.string()),
    timestamp: v.number(),
  },
  handler: async (ctx, args) => {
    await ctx.db.insert("jobLogs", args);
  },
});

export const list = query({
  args: { status: v.optional(v.string()), limit: v.optional(v.number()) },
  handler: async (ctx, { limit }) => {
    return ctx.db.query("hydrationJobs")
      .withIndex("by_created")
      .order("desc")
      .take(limit ?? 50);
  },
});

export const listByProject = query({
  args: { projectSlug: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, { projectSlug, limit }) => {
    const project = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", projectSlug)).first();
    if (!project) return [];
    return ctx.db.query("hydrationJobs")
      .withIndex("by_project", (q) => q.eq("projectId", project._id))
      .order("desc")
      .take(limit ?? 50);
  },
});

export const get = query({
  args: { jobId: v.id("hydrationJobs") },
  handler: async (ctx, { jobId }) => ctx.db.get(jobId),
});

export const getLogs = query({
  args: {
    jobId: v.string(),
    afterSeq: v.optional(v.number()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, { jobId, afterSeq, limit }) => {
    let q = ctx.db.query("jobLogs").withIndex("by_job_seq", (q) => q.eq("jobId", jobId));
    if (afterSeq !== undefined) {
      q = ctx.db.query("jobLogs").withIndex("by_job_seq", (q) =>
        q.eq("jobId", jobId).gt("seq", afterSeq)
      );
    }
    return q.take(limit ?? 200);
  },
});
