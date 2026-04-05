with open("packages/api/app/routers/analysis.py", "r") as f:
    content = f.read()

content = content.replace("project_id", "project_slug")
content = content.replace('"projectId": project_slug,', '"projectSlug": project_slug,')
content = content.replace('alias="projectId"', 'alias="projectSlug"')

with open("packages/api/app/routers/analysis.py", "w") as f:
    f.write(content)
