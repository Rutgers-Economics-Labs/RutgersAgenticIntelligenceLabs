with open("packages/web/app/[project]/quality/page.tsx", "r") as f:
    content = f.read()

parts = content.split("export default ")
if len(parts) > 2:
    content = parts[0] + parts[1] + "export default " + parts[2]

with open("packages/web/app/[project]/quality/page.tsx", "w") as f:
    f.write(content)
