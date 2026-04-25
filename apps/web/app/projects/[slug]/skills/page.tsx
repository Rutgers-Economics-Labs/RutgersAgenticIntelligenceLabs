import { fetchProjectSkills } from "@/lib/api";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { SkillList, InlineStatus } from "@/components/command-center";

export default async function SkillsPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { skills, summary } = await fetchProjectSkills(slug);
  const roles = Array.isArray(summary.agentRolesWithSkillAccess) ? summary.agentRolesWithSkillAccess as string[] : [];

  const rightRail = (
    <div>
      <SectionCard eyebrow="Skill Access" noPad>
        <InlineStatus label="skills" value={skills.length} />
        <InlineStatus label="enabled roles" value={roles.length} />
        {roles.map((role) => <InlineStatus key={role} label={role} value="enabled" />)}
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Skills" section="skills" rightRail={rightRail}>
      <SectionCard eyebrow="Repo Skills" title="Agent playbooks" noPad>
        <SkillList skills={skills} />
      </SectionCard>
    </ProjectShell>
  );
}
