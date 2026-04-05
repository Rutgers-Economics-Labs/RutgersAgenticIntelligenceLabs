import re
import glob

# Ensure all 'export default function Page' become 'export default async function Page' in the new directories
for filepath in glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True):
    with open(filepath, "r") as f:
        content = f.read()

    # We must explicitly look for "export default function" and replace it, bypassing the regex which may have failed if it matched something else
    content = content.replace("export default function ", "export default async function ")
    content = content.replace("export default async async function ", "export default async function ")

    with open(filepath, "w") as f:
        f.write(content)
