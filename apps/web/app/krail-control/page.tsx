import { KrailControl } from "@/components/krail-control/krail-control";
import { asResource, createServerKrailApiClient } from "@/lib/krail/api/server";

export const dynamic = "force-dynamic";

export default async function KrailControlPage() {
  const api = createServerKrailApiClient();
  const [projects, execution] = await Promise.all([
    asResource(() => api.listProjects()),
    asResource(() => api.getExecutionCapabilities()),
  ]);
  return <KrailControl projects={projects} execution={execution} />;
}
