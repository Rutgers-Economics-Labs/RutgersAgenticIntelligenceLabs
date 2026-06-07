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
    <section className="section-card-surface">
      {(eyebrow || title) && (
        <div className="section-card-header">
          {eyebrow && (
            <span className="rail-label">{eyebrow}</span>
          )}
          {title && (
            <span className="section-card-title">{title}</span>
          )}
        </div>
      )}
      <div className={noPad ? undefined : "section-card-body"}>
        {children}
      </div>
    </section>
  );
}
