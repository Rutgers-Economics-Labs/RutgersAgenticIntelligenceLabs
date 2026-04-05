import re

with open("packages/web/app/[project]/agent/page.tsx", "r") as f:
    content = f.read()

# I am replacing literally
content = content.replace("export default function WorkspacePage({ params }: { params: { project: string } }) {", "export default async function WorkspacePage({ params }: { params: Promise<{ project: string }> }) {")

with open("packages/web/app/[project]/agent/page.tsx", "w") as f:
    f.write(content)
