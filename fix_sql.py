import re

with open("packages/web/app/[project]/sql/page.tsx", "r") as f:
    content = f.read()

# Replace SqlPageInner() with SqlPageInner({ projectSlug }: { projectSlug: string })
content = re.sub(r'function SqlPageInner\(\)\s*\{', r'function SqlPageInner({ projectSlug }: { projectSlug: string }) {', content)

with open("packages/web/app/[project]/sql/page.tsx", "w") as f:
    f.write(content)
