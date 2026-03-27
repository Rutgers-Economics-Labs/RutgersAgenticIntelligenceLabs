import { Suspense } from "react";
import EntityDetailClient from "./EntityDetailClient";

function safeDecodeURIComponent(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export default async function EntityDetailPage(props: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ projectId?: string }>;
}) {
  const params = await props.params;
  const searchParams = await props.searchParams;

  // Next will hand us the decoded segment in many cases, but be tolerant of either.
  const id = safeDecodeURIComponent(params.id);
  const projectId = searchParams?.projectId;

  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading entity...</div>}>
      <EntityDetailClient id={id} projectId={projectId} />
    </Suspense>
  );
}
