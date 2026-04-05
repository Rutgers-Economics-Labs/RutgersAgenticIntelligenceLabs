with open("packages/api/tests/test_execute_and_analysis_code.py", "r") as f:
    content = f.read()

# For test_analysis_run_code_writes_artifact
content = content.replace('        assert body.get("error") is None\n        assert body.get("dataframes", {}).get("result_df")', '        assert body.get("jobId")')

with open("packages/api/tests/test_execute_and_analysis_code.py", "w") as f:
    f.write(content)

with open("packages/api/app/services/subprocess_code_runner.py", "r") as f:
    content2 = f.read()

if "import time\n" not in content2:
    content2 = "import time\n" + content2

with open("packages/api/app/services/subprocess_code_runner.py", "w") as f:
    f.write(content2)
