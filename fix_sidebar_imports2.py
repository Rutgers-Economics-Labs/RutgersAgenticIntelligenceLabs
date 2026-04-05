import re

with open("packages/web/components/layout/Sidebar.tsx", "r") as f:
    content = f.read()

# Make sure LayoutDashboard is imported
if "LayoutDashboard" not in content[:content.find("const NAV_GROUPS")]:
    content = content.replace("ShieldCheck,", "ShieldCheck, LayoutDashboard,")

with open("packages/web/components/layout/Sidebar.tsx", "w") as f:
    f.write(content)
