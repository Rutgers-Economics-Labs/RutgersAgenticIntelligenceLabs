from fastapi.testclient import TestClient
from packages.api.app.main import app

client = TestClient(app)

response = client.get("/api/v1/ontology/schema?project=test_project")
print(response.status_code)
print(response.json())
