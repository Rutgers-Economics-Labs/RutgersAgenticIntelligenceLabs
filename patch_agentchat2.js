const fs = require("fs");

let content = fs.readFileSync("packages/web/components/agent/AgentChat.tsx", "utf-8");

content = content.replace(
  `        } else if (event.type === "tool_call") {`,
  `        } else if (event.type === "role_change") {
          onMessages(prev => prev.map(m =>
            m.id === asstId
              ? { ...m, agentRole: event.agentRole }
              : m
          ));
        } else if (event.type === "tool_call") {`
);

content = content.replace(
  `            return {
              ...m,
              toolCalls: [...(m.toolCalls ?? []), { id: event.id, name: event.name, args: event.args }],
            };`,
  `            return {
              ...m,
              toolCalls: [...(m.toolCalls ?? []), { id: event.id, name: event.name, args: event.args, agentRole: event.agentRole }],
            };`
);

fs.writeFileSync("packages/web/components/agent/AgentChat.tsx", content);
