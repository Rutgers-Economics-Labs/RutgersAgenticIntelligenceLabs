import re

with open("packages/web/convex/quality.ts", "r") as f:
    content = f.read()

content = content.replace("projectId: v.optional(v.id(\"projects\"))", "projectSlug: v.optional(v.string())")
content = content.replace("projectId: v.id(\"projects\")", "projectSlug: v.string()")
content = content.replace('q.eq("projectId", projectId)', 'q.eq("projectSlug", projectSlug)')
content = content.replace('args: { projectId', 'args: { projectSlug')
content = content.replace('({ projectId,', '({ projectSlug,')
content = content.replace('(ctx, { projectId,', '(ctx, { projectSlug,')
content = content.replace('(ctx, { projectId })', '(ctx, { projectSlug })')
content = content.replace('projectId,', 'projectSlug,')
content = content.replace('projectId:', 'projectSlug:')
content = content.replace('q.eq("projectId"', 'q.eq("projectSlug"')
content = content.replace('!projectId', '!projectSlug')
content = content.replace('projectId ===', 'projectSlug ===')

with open("packages/web/convex/quality.ts", "w") as f:
    f.write(content)
