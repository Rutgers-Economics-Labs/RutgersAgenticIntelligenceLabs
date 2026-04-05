import glob
import re

for filepath in glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True):
    with open(filepath, "r") as f:
        content = f.read()

    # Find where 'export default' is and make sure it has 'async'
    content = re.sub(r'export default function (\w+)\(', r'export default async function \1(', content)

    with open(filepath, "w") as f:
        f.write(content)
