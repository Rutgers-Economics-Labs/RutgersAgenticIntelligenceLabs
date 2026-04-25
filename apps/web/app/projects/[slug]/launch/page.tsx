import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
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
      <ResearchLaunchWizard slug={slug} />
    </ProjectShell>
  );
}
