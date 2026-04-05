import os
import re

def update_file(filepath):
    if not os.path.exists(filepath):
        print(f"Not found: {filepath}")
        return
    with open(filepath, "r") as f:
        content = f.read()

    # Check if component exports a default function
    # It probably doesn't take params natively. Next.js page takes `{ params }: { params: { project: string } }`

    original_content = content

    # Find the default export
    match = re.search(r'export default function (\w+)\(\)', content)
    if match:
        func_name = match.group(1)
        content = content.replace(f"export default function {func_name}() {{",
                                f"export default function {func_name}({{ params }}: {{ params: {{ project: string }} }}) {{")

    # We might need to pass `params.project` to inner content functions instead of them using `useSearchParams`.
    # `explorer`'s `ExplorerContent` doesn't take props right now.

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
    update_file(p)
