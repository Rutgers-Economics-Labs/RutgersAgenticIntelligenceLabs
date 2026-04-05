import re
import glob

# Ensure all default exports are async if they use await
for filepath in glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True):
    with open(filepath, "r") as f:
        content = f.read()

    # Find the default export line
    match = re.search(r'export default function (\w+)\(', content)
    if match:
        func_name = match.group(1)
        # If it uses await, make it async
        if "await" in content.split(f"export default function {func_name}")[1]:
            content = content.replace(f"export default function {func_name}(", f"export default async function {func_name}(")

    with open(filepath, "w") as f:
        f.write(content)
