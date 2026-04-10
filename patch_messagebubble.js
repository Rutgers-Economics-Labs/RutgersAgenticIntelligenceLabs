const fs = require("fs");

let content = fs.readFileSync("packages/web/components/agent/AgentChat.tsx", "utf-8");

content = content.replace(
  `function MessageBubble({ msg }: { msg: Message }) {`,
  `function MessageBubble({ msg, isExpertMode }: { msg: Message; isExpertMode?: boolean }) {`
);

content = content.replace(
  `{msg.toolCalls.map(tc => (
              <ToolCallCard key={tc.id} tc={tc} />
            ))}`,
  `{msg.toolCalls.map(tc => (
              <ToolCallCard key={tc.id} tc={tc} isExpertMode={isExpertMode} />
            ))}`
);

fs.writeFileSync("packages/web/components/agent/AgentChat.tsx", content);
