with open("packages/api/tests/conftest.py", "r") as f:
    content = f.read()

content = content.replace('mock.post("/api/mutation").mock(\n            return_value=httpx.Response(200, json={"value": {}})\n        )', 'mock.post("/api/mutation").mock(\n            return_value=httpx.Response(200, json={"value": {"jobId": "test_job_123"}})\n        )')

with open("packages/api/tests/conftest.py", "w") as f:
    f.write(content)
