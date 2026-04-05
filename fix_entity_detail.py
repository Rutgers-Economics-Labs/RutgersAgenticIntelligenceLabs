with open("packages/web/app/[project]/ontology/classes/[id]/EntityDetailClient.tsx", "r") as f:
    content = f.read()

content = content.replace("projectId?: string", "projectSlug?: string")
content = content.replace("projectId,", "projectSlug,")
content = content.replace("projectId: projectId", "projectSlug: projectSlug")

import re
content = re.sub(r'\bprojectId\b', 'projectSlug', content)

with open("packages/web/app/[project]/ontology/classes/[id]/EntityDetailClient.tsx", "w") as f:
    f.write(content)
