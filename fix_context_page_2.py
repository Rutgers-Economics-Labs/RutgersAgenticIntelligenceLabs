with open("packages/web/app/[project]/context/page.tsx", "r") as f:
    content = f.read()

# Fix the use client issue and remove duplicate default export
if 'import { Suspense } from "react";\n"use client";' in content:
    content = content.replace('import { Suspense } from "react";\n"use client";', '"use client";\nimport { Suspense } from "react";')

content = content.replace("export default async function ContextPageInner", "function ContextPageInner")

with open("packages/web/app/[project]/context/page.tsx", "w") as f:
    f.write(content)
