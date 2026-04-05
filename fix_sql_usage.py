import re

with open("packages/web/app/[project]/sql/page.tsx", "r") as f:
    content = f.read()

content = content.replace("<SqlPageInner />", "<SqlPageInner projectSlug={params.project} />")

with open("packages/web/app/[project]/sql/page.tsx", "w") as f:
    f.write(content)
