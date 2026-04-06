import { Suspense } from "react";
import EntityDetailClient from "@/app/[project]/ontology/classes/[id]/EntityDetailClient";

function safeDecodeURIComponent(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export default async function ExplorerEntityPage(props: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ projectSlug?: string; projectId?: string }>;
}) {
  const params = await props.params;
  const searchParams = await props.searchParams;

  const id = safeDecodeURIComponent(params.id);
  const projectSlug = searchParams?.projectSlug?.trim() || searchParams?.projectId?.trim();

  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading entity...</div>}>
      <EntityDetailClient id={id} projectSlug={projectSlug} />
    </Suspense>
  );
}
