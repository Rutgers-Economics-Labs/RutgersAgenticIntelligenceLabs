with open("packages/web/components/layout/Sidebar.tsx", "r") as f:
    lines = f.readlines()

# The file got appended instead of replacing or correctly defining components, which caused import duplication.
# Actually, the modify_sidebar.py earlier appended the imports at the end of the file.

with open("packages/web/components/layout/Sidebar.tsx", "w") as f:
    for i, line in enumerate(lines):
        # Let's just stop rewriting if we see the appended imports block
        if "import Link from" in line and i > 250:
            break
        f.write(line)
