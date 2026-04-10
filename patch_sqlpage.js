const fs = require("fs");

let content = fs.readFileSync("packages/web/app/[project]/sql/page.tsx", "utf-8");

content = content.replace(
  `const [schema, setSchema] = useState<Record<string, { name: string; type: string }[]>>({});`,
  `const [schema, setSchema] = useState<Record<string, { columns: { name: string; type: string; density?: number }[]; row_count?: number }>>({});`
);

content = content.replace(
  `                  {Object.entries(schema).map(([table, columns]) => (`,
  `                  {Object.entries(schema).map(([table, tableData]) => {
                    const columns = tableData.columns || [];
                    return (`
);

content = content.replace(
  `                      </div>
                    </div>
                  ))}`,
  `                      </div>
                    </div>
                  )}
                  )}`
);

fs.writeFileSync("packages/web/app/[project]/sql/page.tsx", content);
