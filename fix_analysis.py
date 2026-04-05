with open("packages/web/app/[project]/analysis/page.tsx", "r") as f:
    content = f.read()

# Make it accept projectSlug from props instead of reading it
content = content.replace("function AnalysisPageInner() {", "function AnalysisPageInner({ projectSlug }: { projectSlug: string }) {")
content = content.replace('const projectSlug = searchParams.get("projectSlug") as Id<"projects"> | null;', '')
content = content.replace("<AnalysisPageInner />", "<AnalysisPageInner projectSlug={(await params).project} />")

with open("packages/web/app/[project]/analysis/page.tsx", "w") as f:
    f.write(content)
