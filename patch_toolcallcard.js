const fs = require("fs");

let content = fs.readFileSync("packages/web/components/agent/AgentChat.tsx", "utf-8");

content = content.replace(
  `function ToolCallCard({ tc }: { tc: ToolCallBlock }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[tc.name] ?? tc.name;

  return (
    <div className="my-1 rounded border border-[--border] bg-[--muted]/40 text-xs">`,
  `function ToolCallCard({ tc, isExpertMode = false }: { tc: ToolCallBlock; isExpertMode?: boolean }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[tc.name] ?? tc.name;

  if (!isExpertMode) {
    return null;
  }

  return (
    <div className="my-1 rounded border border-[--border] bg-[--muted]/40 text-xs">`
);

fs.writeFileSync("packages/web/components/agent/AgentChat.tsx", content);
