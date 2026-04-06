/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as agent from "../agent.js";
import type * as analysis from "../analysis.js";
import type * as configs from "../configs.js";
import type * as connectors from "../connectors.js";
import type * as context from "../context.js";
import type * as executions from "../executions.js";
import type * as jobs from "../jobs.js";
import type * as ontologyTemplates from "../ontologyTemplates.js";
import type * as projectChats from "../projectChats.js";
import type * as projects from "../projects.js";
import type * as quality from "../quality.js";
import type * as questionSessions from "../questionSessions.js";
import type * as registry from "../registry.js";
import type * as schedules from "../schedules.js";
import type * as workspaces from "../workspaces.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  agent: typeof agent;
  analysis: typeof analysis;
  configs: typeof configs;
  connectors: typeof connectors;
  context: typeof context;
  executions: typeof executions;
  jobs: typeof jobs;
  ontologyTemplates: typeof ontologyTemplates;
  projectChats: typeof projectChats;
  projects: typeof projects;
  quality: typeof quality;
  questionSessions: typeof questionSessions;
  registry: typeof registry;
  schedules: typeof schedules;
  workspaces: typeof workspaces;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {};
