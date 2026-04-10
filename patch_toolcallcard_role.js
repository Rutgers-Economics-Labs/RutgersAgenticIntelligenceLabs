const fs = require("fs");

let content = fs.readFileSync("packages/web/components/agent/AgentChat.tsx", "utf-8");

content = content.replace(
  `        <span className="font-medium text-[--primary]">{label}</span>`,
  `        <span className="font-medium text-[--primary]">
          {tc.agentRole && <span className="text-[--muted-foreground] uppercase tracking-wider text-[10px] mr-2">[{tc.agentRole}]</span>}
          {label}
        </span>`
);

fs.writeFileSync("packages/web/components/agent/AgentChat.tsx", content);
