const fs = require("fs");

let content = fs.readFileSync("packages/web/components/agent/AgentChat.tsx", "utf-8");

content = content.replace(
  `export function AgentChat({`,
  `export function AgentChat({`
);

content = content.replace(
  `const isEmpty = messages.length === 0;`,
  `const isEmpty = messages.length === 0;\n  const [isExpertMode, setIsExpertMode] = useState(false);`
);

content = content.replace(
  `{messages.map(msg => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}`,
  `{messages.map(msg => (
          <MessageBubble key={msg.id} msg={msg} isExpertMode={isExpertMode} />
        ))}`
);

content = content.replace(
  `<div className="shrink-0 px-6 pb-6 relative">`,
  `<div className="flex justify-end px-4 py-2">
        <label className="flex items-center gap-2 text-xs text-[--muted-foreground] cursor-pointer">
          <input
            type="checkbox"
            checked={isExpertMode}
            onChange={(e) => setIsExpertMode(e.target.checked)}
            className="rounded border-[--border] bg-[--background] text-[--primary] focus:ring-[--primary]"
          />
          Expert Mode
        </label>
      </div>
      <div className="shrink-0 px-6 pb-6 relative">`
);

fs.writeFileSync("packages/web/components/agent/AgentChat.tsx", content);
