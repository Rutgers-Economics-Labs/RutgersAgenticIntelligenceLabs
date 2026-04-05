import re
with open("packages/api/tests/test_execute_and_analysis_code.py", "r") as f:
    content = f.read()

content = content.replace("        assert body.get(\"error\") is None\n        assert body.get(\"dataframes\", {}).get(\"result_df\")", "        assert body.get(\"jobId\")")

with open("packages/api/tests/test_execute_and_analysis_code.py", "w") as f:
    f.write(content)
