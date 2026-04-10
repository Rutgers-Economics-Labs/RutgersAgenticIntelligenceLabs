const fs = require("fs");

let content = fs.readFileSync("packages/web/app/[project]/overview/page.tsx", "utf-8");

content = content.replace(
  `{lastJob.machine || "unknown"}`,
  `{(lastJob as any).machine || "unknown"}`
);

fs.writeFileSync("packages/web/app/[project]/overview/page.tsx", content);
