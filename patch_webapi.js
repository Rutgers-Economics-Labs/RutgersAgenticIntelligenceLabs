const fs = require("fs");

let content = fs.readFileSync("packages/web/lib/api.ts", "utf-8");

content = content.replace(
  `  schema: (projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<Record<string, { name: string; type: string }[]>>(\`/sql/schema\${params.size ? \`?\${params}\` : ""}\`);
  },`,
  `  schema: (projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<Record<string, { columns: { name: string; type: string; density?: number }[]; row_count?: number }>>(\`/sql/schema\${params.size ? \`?\${params}\` : ""}\`);
  },`
);

fs.writeFileSync("packages/web/lib/api.ts", content);
