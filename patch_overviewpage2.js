const fs = require("fs");

let content = fs.readFileSync("packages/web/app/[project]/overview/page.tsx", "utf-8");

content = content.replace(
  `{lastJob && (lastJob.status === "success" || lastJob.status === "completed") && (`,
  `{lastJob && ((lastJob.status as string) === "success" || lastJob.status === "completed") && (`
);

fs.writeFileSync("packages/web/app/[project]/overview/page.tsx", content);
