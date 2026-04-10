const fs = require("fs");

let content = fs.readFileSync("packages/api/tests/test_storage_and_uploaded_data.py", "utf-8");

content = content.replace(
  `"ontology": "core"`,
  `"ontology": "core.yaml"`
);
content = content.replace(
  `"ontology": "core"`,
  `"ontology": "core.yaml"`
);

fs.writeFileSync("packages/api/tests/test_storage_and_uploaded_data.py", content);

let jobsContent = fs.readFileSync("packages/api/tests/test_jobs_router.py", "utf-8");
jobsContent = jobsContent.replace(
    `{"slug": "core", "content": "classes:\\n  - name: State\\n  - name: County"}`,
    `{"slug": "core", "content": "classes:\\n  - name: NotARealClass\\n  - name: County"}`
);
jobsContent = jobsContent.replace(
    `{"slug": "core", "content": "classes:\\n  - name: State\\n  - name: County"}`,
    `{"slug": "core", "content": "classes:\\n  - name: NotARealClass\\n  - name: County"}`
);
jobsContent = jobsContent.replace(
    `{"slug": "core", "content": "classes:\\n  - name: State\\n  - name: County"}`,
    `{"slug": "core", "content": "classes:\\n  - name: NotARealClass\\n  - name: County"}`
);
jobsContent = jobsContent.replace(
    `{"slug": "core", "content": "classes:\\n  - name: State\\n  - name: County"}`,
    `{"slug": "core", "content": "classes:\\n  - name: NotARealClass\\n  - name: County"}`
);
fs.writeFileSync("packages/api/tests/test_jobs_router.py", jobsContent);
