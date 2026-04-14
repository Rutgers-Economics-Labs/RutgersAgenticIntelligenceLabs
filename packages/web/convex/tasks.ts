import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Task event types that are considered "sync triggers" (kept in sync with planner_sync.py).
const SYNC_TRIGGER_EVENTS = new Set([
  "created",
  "moved_to_ready",
  "approval_requested",
  "approval_granted",
  "runner_started",
  "blocked",
  "verification_passed",
  "done",
]);

export const get = query({
  args: { taskId: v.id("tasks") },
  handler: async (ctx, { taskId }) => ctx.db.get(taskId),
});

export const listByProject = query({
  args: { projectId: v.id("projects"), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, limit = 200 }) => {
    return ctx.db
      .query("tasks")
      .withIndex("by_project", (q) => q.eq("projectId", projectId))
      .order("desc")
      .take(limit);
  },
});

export const listByBoard = query({
  args: { boardId: v.id("taskBoards") },
  handler: async (ctx, { boardId }) => {
    return ctx.db.query("tasks").withIndex("by_board", (q) => q.eq("boardId", boardId)).order("desc").collect();
  },
});

export const create = mutation({
  args: {
    boardId: v.id("taskBoards"),
    projectId: v.id("projects"),
    sessionId: v.optional(v.string()),
    title: v.string(),
    description: v.string(),
    status: v.string(),
    priority: v.optional(v.string()),
    agentRole: v.string(),
    runner: v.optional(v.string()),
    repoPaths: v.array(v.string()),
    acceptanceCriteria: v.array(v.string()),
    dependsOnTaskIds: v.array(v.id("tasks")),
    approvalState: v.optional(v.string()),
    gitSnapshotPath: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("tasks", { ...args, createdAt: now, updatedAt: now });
  },
});

export const update = mutation({
  args: {
    taskId: v.id("tasks"),
    title: v.optional(v.string()),
    description: v.optional(v.string()),
    status: v.optional(v.string()),
    priority: v.optional(v.string()),
    runner: v.optional(v.string()),
    repoPaths: v.optional(v.array(v.string())),
    acceptanceCriteria: v.optional(v.array(v.string())),
    approvalState: v.optional(v.string()),
    gitSnapshotPath: v.optional(v.string()),
  },
  handler: async (ctx, { taskId, ...fields }) => {
    const patch = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined));
    await ctx.db.patch(taskId, { ...patch, updatedAt: Date.now() });
  },
});

/**
 * Atomic task state transition: updates status, records a task event, and
 * signals whether the caller should trigger a Git planner file mirror.
 *
 * Returns { task, shouldSync } so the Python planner can decide whether to
 * call PlannerSync.sync_on_transition() after this mutation completes.
 */
export const transition = mutation({
  args: {
    taskId: v.id("tasks"),
    newStatus: v.string(),
    eventType: v.string(),
    eventPayload: v.optional(v.any()),
    gitSnapshotPath: v.optional(v.string()),
  },
  handler: async (ctx, { taskId, newStatus, eventType, eventPayload, gitSnapshotPath }) => {
    const now = Date.now();
    const patch: Record<string, unknown> = { status: newStatus, updatedAt: now };
    if (gitSnapshotPath !== undefined) patch.gitSnapshotPath = gitSnapshotPath;
    await ctx.db.patch(taskId, patch);

    await ctx.db.insert("taskEvents", {
      taskId,
      eventType,
      payload: eventPayload ?? {},
      createdAt: now,
    });

    const task = await ctx.db.get(taskId);
    return { task, shouldSync: SYNC_TRIGGER_EVENTS.has(eventType) };
  },
});
