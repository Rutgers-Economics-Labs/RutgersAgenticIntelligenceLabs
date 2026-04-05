import re
import glob

# Ensure all 'export default function Page' become 'export default async function Page' in the new directories
for filepath in glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True):
    with open(filepath, "r") as f:
        content = f.read()

    content = re.sub(r'export default function (\w+)\(', r'export default async function \1(', content)

    with open(filepath, "w") as f:
        f.write(content)
