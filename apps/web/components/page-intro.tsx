import Link from "next/link";

type PageIntroAction = {
  label: string;
  href: string;
};

export function PageIntro({
  eyebrow = "Page Purpose",
  title,
  detail,
  actions = [],
}: {
  eyebrow?: string;
  title: string;
  detail: string;
  actions?: PageIntroAction[];
}) {
  return (
    <div className="page-intro">
      <div className="page-intro-copy">
        <div className="rail-label">{eyebrow}</div>
        <div className="page-intro-title">{title}</div>
        <p className="page-intro-detail">{detail}</p>
      </div>
      {actions.length ? (
        <div className="page-intro-actions">
          {actions.map((action) => (
            <Link key={action.href} href={action.href as any} className="page-intro-link">
              {action.label}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
