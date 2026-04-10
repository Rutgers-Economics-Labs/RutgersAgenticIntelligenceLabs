const fs = require("fs");

let content = fs.readFileSync("packages/web/app/[project]/agent/page.tsx", "utf-8");

content = content.replace(
  `        const tables = Object.entries(schema).map(([table, columns]) => {
          const cols = columns.map((column) => \`\${column.name}\`).join(", ");
          return \`\${table}(\${cols})\`;
        });`,
  `        const tables = Object.entries(schema).map(([table, tableData]) => {
          const columns = tableData.columns || [];
          const cols = columns.map((column) => \`\${column.name}\`).join(", ");
          return \`\${table}(\${cols})\`;
        });`
);

fs.writeFileSync("packages/web/app/[project]/agent/page.tsx", content);
