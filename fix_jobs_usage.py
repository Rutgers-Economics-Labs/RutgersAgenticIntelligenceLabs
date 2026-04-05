with open("packages/web/app/(dashboard)/projects/[slug]/page.tsx", "r") as f:
    content = f.read()

content = content.replace("projectId: project._id", "projectSlug: project.slug")

with open("packages/web/app/(dashboard)/projects/[slug]/page.tsx", "w") as f:
    f.write(content)
