import glob

for filepath in glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True):
    with open(filepath, "r") as f:
        content = f.read()

    content = content.replace("export default function ", "export default async function ")
    content = content.replace("export default async async function ", "export default async function ")

    # Check if params is Promise
    content = content.replace("params: { project: string }", "params: Promise<{ project: string }>")

    with open(filepath, "w") as f:
        f.write(content)
