import re
import glob

# In Next.js 15+ (App Router), route params are passed as Promises to layouts and pages,
# requiring `params: Promise<{ project: string }>`

def process_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # Layouts and pages
    content = content.replace("params: { project: string }", "params: Promise<{ project: string }>")

    # We also need to await params in the component body since it's a promise now in modern Next.js.
    # However, if it's Next.js 14, params might just be synchronous, but the types suggest `Promise<{ project: string }>`.

    # Actually Next.js 15 requires awaiting. Let's see next version:
    # "Next.js 16.1.6" - yes it definitely requires awaiting.

    # For layout.tsx:
    # export default async function ProjectLayout({ children, params }: { children: React.ReactNode; params: Promise<{ project: string }> }) {
    #   const resolvedParams = await params;
    #   ... resolvedParams.project

    # Let's write a simple regex replacement for the async function layout & pages

    # First convert to async if not already
    content = re.sub(r'export default function (\w+)\(\{\s*params\s*\}\s*:\s*\{\s*params\s*:\s*Promise<\{\s*project:\s*string\s*\}\>\s*\}\)', r'export default async function \1({ params }: { params: Promise<{ project: string }> })', content)
    content = re.sub(r'export default function (\w+)\(\{\s*children\s*,\s*params\s*,\s*\}\s*:\s*\{\s*children:\s*React\.ReactNode;\s*params:\s*Promise<\{\s*project:\s*string\s*\}\>\s*\}\)', r'export default async function \1({ children, params }: { children: React.ReactNode; params: Promise<{ project: string }> })', content)

    # Wait, the `fix_params.py` added `{ params }: { params: { project: string } }`

    with open(filepath, "w") as f:
        f.write(content)

files = glob.glob("packages/web/app/[project]/**/page.tsx", recursive=True) + ["packages/web/app/[project]/layout.tsx"]

for f in files:
    with open(f, "r") as file:
        content = file.read()

    content = content.replace("params: { project: string }", "params: Promise<{ project: string }>")

    # Inject `const { project } = await params;` or `const resolvedParams = await params;` at start of component
    # We replace `params.project` with `(await params).project` for simplicity

    if "async function" not in content and "export default function" in content:
        content = content.replace("export default function", "export default async function")

    content = content.replace("params.project", "(await params).project")

    with open(f, "w") as file:
        file.write(content)
