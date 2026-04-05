with open("packages/web/app/[project]/questions/page.tsx", "r") as f:
    content = f.read()

content = content.replace('const projectSlug = searchParams.get("projectSlug") ?? undefined;', '')

# Also we need to make sure the export default wraps QuestionsPageInner
if "function QuestionsPageInner" not in content:
    content = content.replace("export default async function QuestionsPage({ params }: { params: { project: string } }) {", "export default function QuestionsPageInner({ projectSlug }: { projectSlug: string }) {")

    new_default_export = """
export default async function QuestionsPage({ params }: { params: Promise<{ project: string }> }) {
  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading questions...</div>}>
      <QuestionsPageInner projectSlug={(await params).project} />
    </Suspense>
  );
}
"""
    content += new_default_export

if 'import { Suspense } from "react";\n"use client";' in content:
    content = content.replace('import { Suspense } from "react";\n"use client";', '"use client";\nimport { Suspense } from "react";')

with open("packages/web/app/[project]/questions/page.tsx", "w") as f:
    f.write(content)
