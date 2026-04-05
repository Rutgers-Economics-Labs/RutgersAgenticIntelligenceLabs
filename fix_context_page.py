with open("packages/web/app/[project]/context/page.tsx", "r") as f:
    content = f.read()

# Replace searchParams access
content = content.replace('const projectSlug = searchParams.get("projectSlug") ?? undefined;', '')
content = content.replace("export default async function ContextPage({ params }: { params: { project: string } }) {", "export default function ContextPageInner({ projectSlug }: { projectSlug: string }) {")

# Then we need to create the real default export
new_default_export = """

export default async function ContextPage({ params }: { params: Promise<{ project: string }> }) {
  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading context...</div>}>
      <ContextPageInner projectSlug={(await params).project} />
    </Suspense>
  );
}
"""

content += new_default_export

# Make sure Suspense is imported
if "import { Suspense" not in content:
    content = 'import { Suspense } from "react";\n' + content

with open("packages/web/app/[project]/context/page.tsx", "w") as f:
    f.write(content)
