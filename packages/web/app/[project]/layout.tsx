import { TopBar } from "@/components/layout/TopBar";
import { PlannerPlane } from "@/components/project/PlannerPlane";
import { ArtifactPlane } from "@/components/project/ArtifactPlane";
import { ProjectNav } from "@/components/project/ProjectNav";
import { 
  ResizableHandle, 
  ResizablePanel, 
  ResizablePanelGroup 
} from "@/components/ui/resizable";

// Since resizable is not in components/ui yet, I'll implement a simple version or
// just use the library directly if I can't find the shadcn wrapper.
// Actually, I'll implement the shadcn-like wrapper for resizable panels.

export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ project: string }>;
}) {
  const { project: projectSlug } = await params;

  return (
    <div className="flex h-screen flex-col bg-background text-foreground overflow-hidden">
      {/* Global Top Bar */}
      <TopBar projectSlug={projectSlug} />
      
      {/* Project Sub-Nav */}
      <div className="h-12 border-b border-[--border] flex items-center px-4 bg-[--muted]/30 shrink-0">
        <ProjectNav projectSlug={projectSlug} />
      </div>

      {/* Three-Pane Shell */}
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup direction="horizontal">
          {/* Left Pane: Planner */}
          <ResizablePanel defaultSize={25} minSize={15} collapsible>
            <PlannerPlane projectSlug={projectSlug} />
          </ResizablePanel>
          
          <ResizableHandle />
          
          {/* Center Pane: Main Content */}
          <ResizablePanel defaultSize={50} minSize={30}>
            <main className="h-full overflow-auto bg-[--card]/30">
              {children}
            </main>
          </ResizablePanel>
          
          <ResizableHandle />
          
          {/* Right Pane: Artifacts */}
          <ResizablePanel defaultSize={25} minSize={15} collapsible>
            <ArtifactPlane projectSlug={projectSlug} />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}
