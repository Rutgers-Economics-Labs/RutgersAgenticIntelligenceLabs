import os
import re

def process_file(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    with open(filepath, "r") as f:
        content = f.read()

    # Let's handle generic replacement of `useSearchParams` -> taking `project` from `params` for `page.tsx`
    # Most components seem to have a top-level `export default function Page()` wrapping a `*Content()` component

    # 1. Update the top level page
    # Replace `<*Content />` with `<*Content projectSlug={params.project} />`
    content = re.sub(r'<(\w+Content)\s*/>', r'<\1 projectSlug={params.project} />', content)

    # Replace `<Suspense fallback={...}>` around it
    # No changes to Suspense needed

    # 2. Update Content components:
    # Change `function XContent() {` to `function XContent({ projectSlug }: { projectSlug: string }) {`
    content = re.sub(r'function\s+(\w+Content)\s*\(\)\s*\{', r'function \1({ projectSlug }: { projectSlug: string }) {', content)

    # 3. Replace useSearchParams usage:
    # Replace `const searchParams = useSearchParams();` with empty string or comment
    content = re.sub(r'const searchParams = useSearchParams\(\);', '', content)

    # 4. Replace `const projectId = searchParams.get("projectId") || undefined;`
    content = re.sub(r'const projectId\s*=\s*searchParams\.get\("projectId"\)(\s*\|\|\s*undefined)?;', '', content)

    # 5. Replace references of `projectId` with `projectSlug`
    content = re.sub(r'\bprojectId\b', 'projectSlug', content)

    # 6. Some pages directly exported function that uses useSearchParams
    if 'useSearchParams' in content and 'Content' not in content:
        # It's directly in the main page
        content = re.sub(r'const searchParams = useSearchParams\(\);', '', content)
        content = re.sub(r'const projectSlug\s*=\s*searchParams\.get\("projectSlug"\)(\s*\|\|\s*undefined)?;', '', content)
        # `params.project` is already passed.

    # Remove `import { useSearchParams } from "next/navigation";`
    content = re.sub(r'import\s+\{\s*useSearchParams\s*\}\s*from\s*"next/navigation";', '', content)

    # Write back
    with open(filepath, "w") as f:
        f.write(content)

pages_to_fix = [
    "packages/web/app/[project]/ontology/classes/page.tsx",
    "packages/web/app/[project]/ontology/classes/[id]/page.tsx",
    "packages/web/app/[project]/ontology/graph/page.tsx",
    "packages/web/app/[project]/sql/page.tsx",
    "packages/web/app/[project]/analysis/page.tsx",
    "packages/web/app/[project]/jobs/page.tsx",
    "packages/web/app/[project]/jobs/[id]/page.tsx",
    "packages/web/app/[project]/quality/page.tsx",
    "packages/web/app/[project]/agent/page.tsx",
    "packages/web/app/[project]/questions/page.tsx",
    "packages/web/app/[project]/context/page.tsx"
]

for p in pages_to_fix:
    process_file(p)
