import { fetchZenMode } from "@/lib/api";
import type { ZenResponse } from "@/lib/types";
import ZenClient from "./client";

type ZenPageProps = {
  params: Promise<{ slug: string }>;
};

export default async function ZenPage({ params }: ZenPageProps) {
  const { slug } = await params;

  let initialData: ZenResponse | null = null;
  let initialError: string | null = null;

  try {
    initialData = await fetchZenMode(slug);
  } catch (error) {
    initialError =
      error instanceof Error && error.message
        ? error.message
        : String(error);
  }

  return (
    <ZenClient
      slug={slug}
      initialData={initialData}
      initialError={initialError}
    />
  );
}
