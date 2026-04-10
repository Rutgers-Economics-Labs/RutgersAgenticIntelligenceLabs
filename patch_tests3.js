const fs = require("fs");

let jobsContent = fs.readFileSync("packages/api/tests/test_jobs_router.py", "utf-8");

jobsContent = jobsContent.replace(
    `def _convex_query_dispatch(request: httpx.Request) -> httpx.Response:`,
    `def _convex_query_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    if path == "configs:getPipeline":
        return httpx.Response(200, json={"value": PIPELINE_DOC})
    if path == "configs:getOntology":
        return httpx.Response(200, json={"value": {"slug": "core", "content": "classes:\\n  - name: State\\n  - name: County"}})
    if path == "configs:getApi":
        return httpx.Response(200, json={"value": {"slug": "census_states", "content": "fake api yaml"}})
    return httpx.Response(200, json={"value": None})
`
);

for(let i=0; i<3; i++) {
jobsContent = jobsContent.replace(
  `def _convex_query_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    if path == "configs:getPipeline":
        return httpx.Response(200, json={"value": PIPELINE_DOC})
    if path == "configs:getOntology":
        return httpx.Response(200, json={"value": {"slug": "core", "content": "classes:\\n  - name: State\\n  - name: County"}})
    if path == "configs:getApi":
        return httpx.Response(200, json={"value": {"slug": "census_states", "content": "fake api yaml"}})
    return httpx.Response(200, json={"value": None})

    payload = json.loads(request.content.decode())`,
  `def _convex_query_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())`
);
}
fs.writeFileSync("packages/api/tests/test_jobs_router.py", jobsContent);

let content = fs.readFileSync("packages/api/tests/test_storage_and_uploaded_data.py", "utf-8");

content = content.replace(
  `         patch("app.services.pipeline_validate.ensure_pipeline_ready", new_callable=AsyncMock) as mock_ready, \\`,
  `         patch("app.services.pipeline_validate.ensure_pipeline_ready", new_callable=AsyncMock, return_value={"pipeline": {"ontology": "core"}, "ontology": {"classes": []}, "apis": {}}) as mock_ready, \\`
);
content = content.replace(
  `         patch("app.services.pipeline_validate.ensure_pipeline_ready", new_callable=AsyncMock), \\`,
  `         patch("app.services.pipeline_validate.ensure_pipeline_ready", new_callable=AsyncMock, return_value={"pipeline": {"ontology": "core"}, "ontology": {"classes": []}, "apis": {}}), \\`
);
fs.writeFileSync("packages/api/tests/test_storage_and_uploaded_data.py", content);
