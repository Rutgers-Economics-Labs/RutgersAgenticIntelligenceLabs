import glob

# The issue is that the replacement didn't work because it's not exactly "export default function "
# or there is something else. Let's just use string replacement on the exact string.

for filepath in glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True):
    with open(filepath, "r") as f:
        content = f.read()

    # We find all `export default function XYZ` and replace with `export default async function XYZ`
    import re
    content = re.sub(r'export default function\s+([A-Za-z0-9_]+)\s*\(', r'export default async function \1(', content)

    # Fix the duplicate asyncs just in case
    content = content.replace("export default async async function", "export default async function")

    with open(filepath, "w") as f:
        f.write(content)
