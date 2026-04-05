with open("packages/web/app/[project]/context/page.tsx", "r") as f:
    content = f.read()

# I see what happened, `fix_context_page.py` appended the new default export
# But the original one might still be there as `export default function ContextPage` before it replaced.
# Let's remove the duplicated one at the bottom.

# In my script: content = content.replace("export default async function ContextPageInner", "function ContextPageInner")
# Oh, the original replacement was: `export default async function ContextPage({ params }: { params: { project: string } }) {` to `export default function ContextPageInner`
# But it probably failed to replace it because it was `export default async function ContextPage`
# So we have two `export default`s.

content = content.replace("export default async function ContextPageInner", "function ContextPageInner")
content = content.replace("export default function ContextPageInner", "function ContextPageInner")

# Let's just make sure there's only ONE `export default`
parts = content.split("export default ")
if len(parts) > 2:
    # Multiple default exports!
    # Let's remove the first one if it's ContextPageInner
    content = parts[0] + parts[1] + "export default " + parts[2]

# Let's verify by just printing how many times `export default` appears
with open("packages/web/app/[project]/context/page.tsx", "w") as f:
    f.write(content)
