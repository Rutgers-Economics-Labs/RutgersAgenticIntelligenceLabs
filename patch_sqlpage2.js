const fs = require("fs");

let content = fs.readFileSync("packages/web/app/[project]/sql/page.tsx", "utf-8");

content = content.replace(
  `{schema[t].slice(0, 8).map(c => (
                    <li key={c.name}>{c.name} <span className="opacity-50">{c.type}</span></li>
                  ))}`,
  `{(schema[t]?.columns || []).slice(0, 8).map(c => (
                    <li key={c.name}>{c.name} <span className="opacity-50">{c.type}</span></li>
                  ))}`
);

content = content.replace(
  `{schema[t].length > 8 && <li className="opacity-50">+{schema[t].length - 8} more</li>}`,
  `{(schema[t]?.columns || []).length > 8 && <li className="opacity-50">+{(schema[t]?.columns || []).length - 8} more</li>}`
);

fs.writeFileSync("packages/web/app/[project]/sql/page.tsx", content);
