const fs = require("fs");

let jobsContent = fs.readFileSync("packages/api/tests/test_jobs_router.py", "utf-8");

jobsContent = jobsContent.replace(
    `def _convex_query_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    if path == "configs:getPipeline":
        return httpx.Response(200, json={"value": PIPELINE_DOC})
    if path == "configs:getApi":
        return httpx.Response(
            200,
            json={"value": {"slug": "census_states", "content": CENSUS_STATES_API_YAML}},
        )
    if path == "configs:getOntology":
        return httpx.Response(200, json={"value": None})
    return httpx.Response(200, json={"value": None})`,
    `def _convex_query_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    if path == "configs:getPipeline":
        return httpx.Response(200, json={"value": PIPELINE_DOC})
    if path == "configs:getOntology":
        return httpx.Response(200, json={"value": {"slug": "core", "content": "classes: []"}})
    if path == "configs:getApi":
        return httpx.Response(
            200,
            json={"value": {"slug": "census_states", "content": CENSUS_STATES_API_YAML}},
        )
    return httpx.Response(200, json={"value": None})`
);

jobsContent = jobsContent.replace(
  `    def dispatch(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        path = payload.get("path")
        if path == "configs:getPipeline":
            return httpx.Response(200, json={"value": bad_pipeline})
        if path == "configs:getApi":
            return httpx.Response(
                200,
                json={"value": {"slug": "census_states", "content": CENSUS_STATES_API_YAML}},
            )
        if path == "configs:getOntology":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})`,
  `    def dispatch(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        path = payload.get("path")
        if path == "configs:getPipeline":
            return httpx.Response(200, json={"value": bad_pipeline})
        if path == "configs:getApi":
            return httpx.Response(
                200,
                json={"value": {"slug": "census_states", "content": CENSUS_STATES_API_YAML}},
            )
        if path == "configs:getOntology":
            return httpx.Response(200, json={"value": {"slug": "core", "content": "classes: []"}})
        return httpx.Response(200, json={"value": None})`
);

fs.writeFileSync("packages/api/tests/test_jobs_router.py", jobsContent);
