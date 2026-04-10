const fs = require("fs");

let content = fs.readFileSync("packages/web/components/agent/AgentChat.tsx", "utf-8");

content = content.replace(
  `        {/* Text content */}`,
  `        {msg.agentRole && (
          <div className="text-xs font-semibold text-[--primary] uppercase tracking-wider mb-2">
            {msg.agentRole} is thinking...
          </div>
        )}
        {/* Text content */}`
);

fs.writeFileSync("packages/web/components/agent/AgentChat.tsx", content);
