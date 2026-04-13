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

export const getBySlug = query({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) =>
    ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", slug)).first(),
});

export const getById = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, { projectId }) => ctx.db.get(projectId),
});

export const getByGithubRepo = query({
  args: { github: v.string() },
  handler: async (ctx, { github }) =>
    ctx.db.query("projects").withIndex("by_github", (q) => q.eq("github", github)).first(),
});

function makeForkSlug(slug: string, suffix: number) {
  return `${slug}-copy-${suffix}`;
}

export const create = mutation({
  args: {
    name: v.string(),
    slug: v.string(),
    description: v.optional(v.string()),
    gitRepoUrl: v.optional(v.string()),
    localRepoPath: v.optional(v.string()),
    manifestPath: v.optional(v.string()),
    approach: v.union(v.literal("data-first"), v.literal("ontology-first")),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return ctx.db.insert("projects", {
      ...args,
      manifestPath: args.manifestPath ?? "rail.yaml",
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
    gitRepoUrl: v.optional(v.string()),
    localRepoPath: v.optional(v.string()),
    manifestPath: v.optional(v.string()),
    ontologyConfigSlug: v.optional(v.string()),
    apiConfigSlugs: v.optional(v.array(v.string())),
    pipelineConfigSlug: v.optional(v.string()),
    status: v.optional(v.union(v.literal("draft"), v.literal("ready"), v.literal("hydrated"))),
    lastJobId: v.optional(v.string()),
    activeOntologyDbPath: v.optional(v.string()),
    activeOntologyOwlPath: v.optional(v.string()),
    activeOntologyDuckdbPath: v.optional(v.string()),
    activeOntologyEmbeddingsPath: v.optional(v.string()),
    github: v.optional(v.string()),
    defaultBranch: v.optional(v.string()),
    ontologyTemplates: v.optional(v.array(v.string())),
    agentModel: v.optional(v.string()),
    agentAllowedActions: v.optional(v.array(v.string())),
    lastHydratedAt: v.optional(v.number()),
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

export const updateById = mutation({
  args: {
    projectId: v.id("projects"),
    name: v.optional(v.string()),
    description: v.optional(v.string()),
    gitRepoUrl: v.optional(v.string()),
    localRepoPath: v.optional(v.string()),
    manifestPath: v.optional(v.string()),
    ontologyConfigSlug: v.optional(v.string()),
    apiConfigSlugs: v.optional(v.array(v.string())),
    pipelineConfigSlug: v.optional(v.string()),
    status: v.optional(v.union(v.literal("draft"), v.literal("ready"), v.literal("hydrated"))),
    lastJobId: v.optional(v.string()),
    activeOntologyDbPath: v.optional(v.string()),
    activeOntologyOwlPath: v.optional(v.string()),
    activeOntologyDuckdbPath: v.optional(v.string()),
    activeOntologyEmbeddingsPath: v.optional(v.string()),
    github: v.optional(v.string()),
    defaultBranch: v.optional(v.string()),
    ontologyTemplates: v.optional(v.array(v.string())),
    agentModel: v.optional(v.string()),
    agentAllowedActions: v.optional(v.array(v.string())),
    lastHydratedAt: v.optional(v.number()),
  },
  handler: async (ctx, { projectId, ...fields }) => {
    const patch = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined));
    await ctx.db.patch(projectId, { ...patch, updatedAt: Date.now() });
  },
});

export const remove = mutation({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) => {
    const doc = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", slug)).first();
    if (doc) await ctx.db.delete(doc._id);
  },
});

export const forkProject = mutation({
  args: {
    projectId: v.id("projects"),
    newName: v.string(),
  },
  handler: async (ctx, { projectId, newName }) => {
    const project = await ctx.db.get(projectId);
    if (!project) throw new Error("Project not found");

    const suffix = Date.now();

    let ontologyConfigSlug = project.ontologyConfigSlug;
    if (project.ontologyConfigSlug) {
      const ontology = await ctx.db
        .query("ontologyConfigs")
        .withIndex("by_slug", (q) => q.eq("slug", project.ontologyConfigSlug!))
        .first();
      if (ontology) {
        const newSlug = makeForkSlug(ontology.slug, suffix);
        await ctx.db.insert("ontologyConfigs", {
          ...ontology,
          slug: newSlug,
          name: `${ontology.name} (copy)`,
          createdAt: Date.now(),
          updatedAt: Date.now(),
        });
        ontologyConfigSlug = newSlug;
      }
    }

    const apiConfigSlugs: string[] = [];
    for (const apiSlug of project.apiConfigSlugs) {
      const apiConfig = await ctx.db
        .query("apiConfigs")
        .withIndex("by_slug", (q) => q.eq("slug", apiSlug))
        .first();
      if (!apiConfig) continue;
      const newSlug = makeForkSlug(apiConfig.slug, suffix);
      await ctx.db.insert("apiConfigs", {
        ...apiConfig,
        slug: newSlug,
        name: `${apiConfig.name} (copy)`,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
      apiConfigSlugs.push(newSlug);
    }

    let pipelineConfigSlug = project.pipelineConfigSlug;
    if (project.pipelineConfigSlug) {
      const pipeline = await ctx.db
        .query("pipelineConfigs")
        .withIndex("by_slug", (q) => q.eq("slug", project.pipelineConfigSlug!))
        .first();
      if (pipeline) {
        const newSlug = makeForkSlug(pipeline.slug, suffix);
        await ctx.db.insert("pipelineConfigs", {
          ...pipeline,
          slug: newSlug,
          name: `${pipeline.name} (copy)`,
          referencedApiSlugs: apiConfigSlugs,
          createdAt: Date.now(),
          updatedAt: Date.now(),
        });
        pipelineConfigSlug = newSlug;
      }
    }

    const newProjectSlug = makeForkSlug(project.slug, suffix);
    const newProjectId = await ctx.db.insert("projects", {
      ...project,
      name: newName,
      slug: newProjectSlug,
      ontologyConfigSlug,
      apiConfigSlugs,
      pipelineConfigSlug,
      status: "draft",
      lastJobId: undefined,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    });

    return { newProjectId, slug: newProjectSlug };
  },
});

export const resetStatus = mutation({
  args: {},
  handler: async (ctx) => {
    const projects = await ctx.db.query("projects").collect();
    for (const p of projects) {
      await ctx.db.patch(p._id, {
        status: "ready",
        activeOntologyDbPath: undefined,
        activeOntologyOwlPath: undefined,
        activeOntologyDuckdbPath: undefined,
        activeOntologyEmbeddingsPath: undefined,
        lastHydratedAt: undefined,
      });
    }
  },
});
