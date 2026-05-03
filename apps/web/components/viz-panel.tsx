"use client";

/**
 * VizPanel — renders an LLM-generated HTML visualization in a sandboxed iframe.
 *
 * The iframe uses srcdoc, which inherits the parent page's origin (localhost:3000),
 * so the generated HTML can call /api/rail-sql as a same-origin fetch.
 */
export function VizPanel({
  html,
  title,
  description,
  height = 280,
}: {
  html: string;
  title: string;
  description?: string;
  height?: number;
}) {
  return (
    <div
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          padding: "10px 16px 8px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="rail-label">viz</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)" }}>
            {title}
          </span>
        </div>
        {description && (
          <div style={{ fontSize: 11, color: "var(--muted)", paddingLeft: 28 }}>
            {description}
          </div>
        )}
      </div>
      <iframe
        srcDoc={html}
        style={{ width: "100%", height, border: "none", display: "block" }}
        sandbox="allow-scripts allow-same-origin"
        title={title}
      />
    </div>
  );
}
