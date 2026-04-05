with open("packages/web/app/[project]/jobs/page.tsx", "r") as f:
    content = f.read()

content = content.replace("function JobsPageInner() {", "function JobsPageInner({ projectSlug }: { projectSlug: string }) {")
content = content.replace('const projectSlug = searchParams.get("projectSlug") as Id<"projects"> | null;', '')
content = content.replace("<JobsPageInner />", "<JobsPageInner projectSlug={(await params).project} />")

with open("packages/web/app/[project]/jobs/page.tsx", "w") as f:
    f.write(content)
