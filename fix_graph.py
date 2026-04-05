with open("packages/web/app/[project]/ontology/graph/page.tsx", "r") as f:
    content = f.read()

content = content.replace("function GraphClient() {", "function GraphClient({ projectSlug }: { projectSlug: string }) {")
content = content.replace("<GraphClient />", "<GraphClient projectSlug={(await params).project} />")

with open("packages/web/app/[project]/ontology/graph/page.tsx", "w") as f:
    f.write(content)
