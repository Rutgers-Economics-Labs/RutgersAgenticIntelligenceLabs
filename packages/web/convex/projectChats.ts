import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const create = mutation({
  args: {
    projectId: v.id("projects"),
    title: v.string(),
    messages: v.array(v.object({
      role: v.union(v.literal("user"), v.literal("assistant")),
      content: v.string(),
    })),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const id = await ctx.db.insert("projectChats", { ...args, createdAt: now, updatedAt: now });
    return { chatId: id };
  },
});

export const appendMessages = mutation({
  args: {
    chatId: v.id("projectChats"),
    messages: v.array(v.object({
      role: v.union(v.literal("user"), v.literal("assistant")),
      content: v.string(),
    })),
  },
  handler: async (ctx, { chatId, messages }) => {
    const chat = await ctx.db.get(chatId);
    if (!chat) throw new Error("Chat not found");
    await ctx.db.patch(chatId, {
      messages: [...chat.messages, ...messages],
      updatedAt: Date.now(),
    });
  },
});

export const updateTitle = mutation({
  args: { chatId: v.id("projectChats"), title: v.string() },
  handler: async (ctx, { chatId, title }) => {
    await ctx.db.patch(chatId, { title, updatedAt: Date.now() });
  },
});

export const remove = mutation({
  args: { chatId: v.id("projectChats") },
  handler: async (ctx, { chatId }) => ctx.db.delete(chatId),
});

export const listByProject = query({
  args: { projectId: v.id("projects"), limit: v.optional(v.number()) },
  handler: async (ctx, { projectId, limit }) =>
    ctx.db.query("projectChats")
      .withIndex("by_project", (q) => q.eq("projectId", projectId))
      .order("desc")
      .take(limit ?? 30),
});

export const get = query({
  args: { chatId: v.id("projectChats") },
  handler: async (ctx, { chatId }) => ctx.db.get(chatId),
});
