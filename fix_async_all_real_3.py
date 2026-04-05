with open("packages/web/app/[project]/analysis/page.tsx", "r") as f:
    content = f.read()
print(repr(content.split("export default")[1][:100]))
