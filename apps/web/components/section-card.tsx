import { ReactNode } from "react";

export function SectionCard({
  eyebrow,
  title,
  children,
  noPad,
}: {
  eyebrow?: string;
  title?: string;
  children: ReactNode;
  noPad?: boolean;
}) {
  return (
    <section style={{
      borderBottom: "1px solid var(--border)",
      background: "var(--panel)",
    }}>
      {(eyebrow || title) && (
        <div style={{
          padding: "10px 16px 8px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "baseline",
          gap: 10,
        }}>
          {eyebrow && (
            <span className="rail-label">{eyebrow}</span>
          )}
          {title && (
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)" }}>{title}</span>
          )}
        </div>
      )}
      <div style={noPad ? {} : { padding: "14px 16px" }}>
        {children}
      </div>
    </section>
  );
}
