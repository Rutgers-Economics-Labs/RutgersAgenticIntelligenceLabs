import re

with open("packages/web/components/analysis/AnalysisWorkspace.tsx", "r") as f:
    content = f.read()

# Fix usage of `projectId` inside AnalysisWorkspace
# Usually they pass `projectId` to API. Since it accepts string `projectSlug` now.
# Wait, let's see where projectId is used
content = content.replace("projectId={projectId}", "projectId={projectId} projectSlug={projectSlug}")
# Also we need to look for `projectId` being passed to `analysis.xxx(..., projectId)` and change to `projectSlug`?
# In python fast api we usually accept project_id. Let's pass projectSlug.
content = re.sub(r'analysis\.execute\((\w+),\s*projectId\)', r'analysis.execute(\1, projectSlug || projectId as string)', content)
content = re.sub(r'analysis\.schema\(\s*projectId\s*\)', r'analysis.schema(projectSlug || projectId as string)', content)
# convex mutations:
content = re.sub(r'projectId: projectId,', r'projectId: projectId!, // TODO FIX SLUG\n      projectSlug: projectSlug,', content)

with open("packages/web/components/analysis/AnalysisWorkspace.tsx", "w") as f:
    f.write(content)
