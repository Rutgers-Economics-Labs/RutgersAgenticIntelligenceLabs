with open("packages/api/app/services/subprocess_code_runner.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip() == "import time" and "Used when" in "".join(lines[:10]):
        continue
    new_lines.append(line)

new_lines.insert(9, "import time\n")

with open("packages/api/app/services/subprocess_code_runner.py", "w") as f:
    f.writelines(new_lines)
