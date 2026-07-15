import { KrailAnalyze } from "@/components/krail-analyze/krail-analyze";
import { asResource, createServerKrailApiClient } from "@/lib/krail/api/server";
import type { ApiError, Project, Resource } from "@/lib/krail/api";
import { capabilityMessage, executeProjectQuery, MAX_QUERY_ROWS, MAX_SQL_LENGTH, type QueryResult } from "@/lib/krail/analyze/query";

export const dynamic = "force-dynamic";

type Search = { project?: string; sql?: string; limit?: string; run?: string };

function selectedProject(projects: Resource<Project[]>, requested?: string): Project | undefined {
  return projects.state === "ready" ? projects.data.find((project) => project.projectId === requested) ?? projects.data[0] : undefined;
}

function boundedLimit(value?: string): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? Math.max(1, Math.min(MAX_QUERY_ROWS, parsed)) : 200;
}

export default async function KrailAnalyzePage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const api = createServerKrailApiClient();
  const projects = await asResource(() => api.listProjects());
  const project = selectedProject(projects, search.project);
  const sql = search.sql?.trim() ?? "";
  const limit = boundedLimit(search.limit);
  let query: Resource<QueryResult> | undefined;
  if (project && search.run === "1" && sql) {
    if (sql.length > MAX_SQL_LENGTH) {
      query = { state: "error", error: { code: "query_too_long", message: `Queries are limited to ${MAX_SQL_LENGTH.toLocaleString()} characters.` } };
    } else {
      const result = await asResource(() => executeProjectQuery(project.projectId, sql, limit));
      if (result.state === "error") {
        const unavailable = capabilityMessage(result.error);
        query = unavailable ? { state: "unavailable", message: unavailable } : result;
      } else query = result;
    }
  } else if (search.run === "1" && !sql) {
    query = { state: "empty", message: "Enter a SQL query before running it." };
  }
  const sources = project ? await asResource(() => api.getSources(project.projectId)) : undefined;
  return <KrailAnalyze projects={projects} selectedProjectId={project?.projectId} sql={sql} limit={limit} query={query} sources={sources} />;
}
