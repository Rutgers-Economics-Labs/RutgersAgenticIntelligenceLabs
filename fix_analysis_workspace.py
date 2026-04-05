with open("packages/web/components/analysis/AnalysisWorkspace.tsx", "r") as f:
    content = f.read()

content = content.replace("projectId: Id<\"projects\">;", "projectId?: Id<\"projects\">; projectSlug?: string;")

with open("packages/web/components/analysis/AnalysisWorkspace.tsx", "w") as f:
    f.write(content)
