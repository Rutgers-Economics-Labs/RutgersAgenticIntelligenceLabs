import re

with open("packages/web/app/[project]/agent/page.tsx", "r") as f:
    content = f.read()

# Replace `SqlPageInner` style leftover in `agent/page.tsx`
# There might be some unresolved `projectSlug`. Let's check `function WorkspacePageInner()` or similar.
content = re.sub(r'function WorkspacePageInner\(\)\s*\{', r'function WorkspacePageInner({ projectSlug }: { projectSlug: string }) {', content)
content = content.replace("<WorkspacePageInner />", "<WorkspacePageInner projectSlug={(await params).project} />")

with open("packages/web/app/[project]/agent/page.tsx", "w") as f:
    f.write(content)
