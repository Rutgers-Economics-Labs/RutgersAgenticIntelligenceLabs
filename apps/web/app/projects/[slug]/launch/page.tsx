import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { PageIntro } from "@/components/page-intro";
import { ResearchLaunchWizard } from "@/components/research-launch-wizard";
import { InlineStatus } from "@/components/command-center";

export default async function LaunchPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const rightRail = (
    <div>
      <SectionCard eyebrow="Launch Policy" noPad>
        <InlineStatus label="writes" value="approval gated" />
        <InlineStatus label="state" value="repo backed" />
        <InlineStatus label="mode" value="preview first" />
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Research Launch" section="launch" rightRail={rightRail}>
      <PageIntro
        title="Start a new work package from a fresh question."
        detail="Use Launch only when you need the planner to break a new idea into initial tasks, roles, and approvals. If the board already exists, stay in Planner."
        actions={[
          { label: "Open Planner", href: `/projects/${slug}/planner` },
          { label: "Open Review", href: `/projects/${slug}/review` },
        ]}
      />
      <ResearchLaunchWizard slug={slug} />
    </ProjectShell>
  );
}
