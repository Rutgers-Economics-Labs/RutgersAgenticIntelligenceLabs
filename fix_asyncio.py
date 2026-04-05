with open("packages/api/app/routers/analysis.py", "r") as f:
    content = f.read()

if "import asyncio\n" not in content:
    content = "import asyncio\n" + content

with open("packages/api/app/routers/analysis.py", "w") as f:
    f.write(content)
