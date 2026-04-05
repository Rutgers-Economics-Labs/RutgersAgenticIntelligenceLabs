with open("packages/web/app/[project]/analysis/page.tsx", "r") as f:
    content = f.read()

# Since `AnalysisPageInner` was changed to pass `projectSlug={projectSlug}`
# Let's make sure it doesn't fail build for `projectSlug` prop type.
content = content.replace("params: { project: string }", "params: Promise<{ project: string }>")
with open("packages/web/app/[project]/analysis/page.tsx", "w") as f:
    f.write(content)
