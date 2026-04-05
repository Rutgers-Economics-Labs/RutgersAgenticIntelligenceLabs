import { ProjectSidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";

export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ project: string }>;
}) {
  return (
    <div className="flex h-screen flex-col">
      <TopBar projectSlug={(await params).project} />
      <div className="flex flex-1 overflow-hidden">
        <ProjectSidebar projectSlug={(await params).project} />
        <main className="flex-1 overflow-auto p-10">{children}</main>
      </div>
    </div>
  );
}
