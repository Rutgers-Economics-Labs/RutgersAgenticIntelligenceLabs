import { fetchPlannerHome, fetchProjectSkills } from "@/lib/api";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { SkillList, InlineStatus } from "@/components/command-center";

export default async function SkillsPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const home = await fetchPlannerHome(slug);
  const skillResult = await fetchProjectSkills(slug)
    .then((value) => ({ ok: true as const, value }))
    .catch(() => ({ ok: false as const }));
  const summary = skillResult.ok
    ? skillResult.value.summary
    : {
        count: Number(home.controlPlane?.skillSummary?.count ?? 0),
        agentRolesWithSkillAccess: home.controlPlane?.skillSummary?.agentRolesWithSkillAccess ?? [],
      };
  const skills = skillResult.ok ? skillResult.value.skills : [];
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
      <SectionCard eyebrow="Advanced Surface" title="Repo playbooks and agent rules">
        <div className="overview-copy" style={{ marginTop: 0 }}>
          Skills are internal playbooks the agents can use while working in this repo. This page is mainly for auditing what guidance exists and which agent roles are allowed to invoke it.
        </div>
      </SectionCard>
      <SectionCard eyebrow="Repo Skills" title="Agent playbooks" noPad>
        {!skillResult.ok && (
          <div className="empty-state" style={{ padding: "12px 16px", borderBottom: skills.length ? "1px solid var(--border-subtle)" : "none" }}>
            Detailed skill inventory is temporarily unavailable. This page is using the repo-backed control-plane summary for role access.
          </div>
        )}
        <SkillList skills={skills} />
      </SectionCard>
    </ProjectShell>
  );
}
