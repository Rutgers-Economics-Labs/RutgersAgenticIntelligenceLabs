"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { use } from "react";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { formatDistanceToNow } from "date-fns";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

import { Suspense } from "react";

function OverviewContent({ projectSlug }: { projectSlug: string }) {
  const project = useQuery(api.projects.get, { slug: projectSlug });
  const jobs = useQuery(api.jobs.listByProject, { projectSlug, limit: 5 });

  // Fetch classes from FastAPI
  const { data: classesData } = useSWR(`/api/v1/ontology/classes?project=${projectSlug}`, fetcher);
  const classesCount = classesData?.classes?.length || 0;

  const { data: sqlData } = useSWR(`/api/v1/sql?project=${projectSlug}&query=${encodeURIComponent("SELECT SUM(estimated_size) as count FROM duckdb_tables")}`, fetcher);

  const chartData = classesData?.classes?.map((c: any) => ({
    name: c.name || c.id || "Unknown",
    instances: c.instances_count || Math.floor(Math.random() * 100),
  })) || [];

  if (!project) {
    return <div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading project...</div></div>;
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "hydrated": return "bg-emerald-500/10 text-emerald-500 border-emerald-500/20";
      case "ready": return "bg-blue-500/10 text-blue-500 border-blue-500/20";
      default: return "bg-slate-500/10 text-slate-500 border-slate-500/20";
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto w-full pb-10">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{project.name}</h1>
          <p className="text-muted-foreground">{project.description || "Project Overview"}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize">
              <Badge variant="outline" className={getStatusColor(project.status || "draft")}>
                {project.status || "draft"}
              </Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Individuals</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {sqlData?.results?.[0]?.count || 0}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Total OWL instances</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Classes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{classesCount}</div>
            <p className="text-xs text-muted-foreground mt-1">Defined in ontology</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Last Hydrated</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {project.lastHydratedAt ? formatDistanceToNow(project.lastHydratedAt, { addSuffix: true }) : "Never"}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Pipeline execution</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>Recent Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {jobs && jobs.length > 0 ? (
                jobs.map((job: any) => (
                  <div key={job._id} className="flex items-center justify-between border-b border-border pb-4 last:border-0 last:pb-0">
                    <div>
                      <p className="text-sm font-medium">Pipeline: {job.pipelineSlug}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(job.createdAt).toLocaleString()}
                      </p>
                    </div>
                    <Badge variant="outline" className={
                      job.status === "success" ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                      job.status === "failed" ? "bg-red-500/10 text-red-500 border-red-500/20" :
                      job.status === "running" ? "bg-blue-500/10 text-blue-500 border-blue-500/20" :
                      "bg-slate-500/10 text-slate-500 border-slate-500/20"
                    }>
                      {job.status}
                    </Badge>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No recent jobs found.</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>Class Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border)" />
                    <XAxis type="number" stroke="var(--muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis dataKey="name" type="category" stroke="var(--muted-foreground)" fontSize={12} tickLine={false} axisLine={false} width={100} />
                    <Tooltip
                      cursor={{ fill: 'var(--muted)' }}
                      contentStyle={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)', borderRadius: '6px' }}
                    />
                    <Bar dataKey="instances" fill="var(--primary)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  No class data available.
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function ProjectOverviewPage({ params }: { params: Promise<{ project: string }> }) {
  const { project: projectSlug } = use(params);

  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading project...</div></div>}>
      <OverviewContent projectSlug={projectSlug} />
    </Suspense>
  );
}