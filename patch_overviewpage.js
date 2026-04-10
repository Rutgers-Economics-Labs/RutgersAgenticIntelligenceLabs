const fs = require("fs");

let content = fs.readFileSync("packages/web/app/[project]/overview/page.tsx", "utf-8");

content = content.replace(
  `                    Sync currently in progress on node <code className="bg-amber-500/10 px-1 rounded font-mono">{activeJob.machine || "unknown"}</code>. Features will unlock once complete.`,
  `                    Sync currently in progress on node <code className="bg-amber-500/10 px-1 rounded font-mono">{(activeJob as any).machine || "unknown"}</code>. Features will unlock once complete.`
);

fs.writeFileSync("packages/web/app/[project]/overview/page.tsx", content);
