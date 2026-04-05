with open("packages/web/app/[project]/agent/page.tsx", "r") as f:
    content = f.read()

# Restore `const searchParams = useSearchParams();` inside `WorkspacePageInner`
# Find `function WorkspacePageInner({ projectSlug }: { projectSlug: string }) {` and insert after

lines = content.split('\n')
for i, line in enumerate(lines):
    if "function WorkspacePageInner({ projectSlug }" in line:
        lines.insert(i + 1, "  const searchParams = useSearchParams();")
        break

# Make sure `useSearchParams` is imported
has_import = any("useSearchParams" in l for l in lines[:20])
if not has_import:
    for i, line in enumerate(lines):
        if line.startswith("import"):
            lines.insert(i, 'import { useSearchParams } from "next/navigation";')
            break

with open("packages/web/app/[project]/agent/page.tsx", "w") as f:
    f.write("\n".join(lines))
