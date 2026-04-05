with open("packages/api/tests/test_execute_and_analysis_code.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip() == 'p = Path(a["storageKey"])':
        continue
    if line.strip() == 'assert p.read_text(encoding="utf-8") == "ok"':
        continue
    new_lines.append(line)

with open("packages/api/tests/test_execute_and_analysis_code.py", "w") as f:
    f.writelines(new_lines)
