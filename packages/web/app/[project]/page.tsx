import { redirect } from "next/navigation";

export default async function ProjectPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = await params;
  redirect(`/${project}/overview`);
}
