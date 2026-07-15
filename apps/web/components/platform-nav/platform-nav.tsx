"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./platform-nav.module.css";

const items = [
  { href: "/", label: "Home" },
  { href: "/krail-explore", label: "Knowledge" },
  { href: "/krail-analyze", label: "Analyze" },
  { href: "/krail-workflows", label: "Workflows" },
  { href: "/krail-control", label: "Projects" },
] as const;

export function PlatformNav() {
  const pathname = usePathname();
  return (
    <header className={styles.shell}>
      <Link className={styles.brand} href="/" aria-label="RAIL home">
        <span className={styles.mark}>R</span>
        <span><strong>RAIL</strong><small>Powered by KRAIL</small></span>
      </Link>
      <nav className={styles.nav} aria-label="Main navigation">
        {items.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return <Link href={item.href} key={item.href} aria-current={active ? "page" : undefined}>{item.label}</Link>;
        })}
      </nav>
      <Link className={styles.setup} href="/krail-control#add-project">Add project</Link>
    </header>
  );
}
