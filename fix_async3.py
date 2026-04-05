import glob

for filepath in glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True):
    with open(filepath, "r") as f:
        content = f.read()

    # The previous regex missed it because it was: export default function WorkspacePage({ params }...
    content = content.replace("export default function", "export default async function")

    with open(filepath, "w") as f:
        f.write(content)
