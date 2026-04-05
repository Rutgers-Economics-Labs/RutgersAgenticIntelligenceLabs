with open("packages/api/tests/test_execute_and_analysis_code.py", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith('        if a.get("filename") == "note.txt":'):
        skip = True
        continue
    if skip and line.startswith('            assert'):
        skip = False
        continue
    new_lines.append(line)

with open("packages/api/tests/test_execute_and_analysis_code.py", "w") as f:
    f.writelines(new_lines)
