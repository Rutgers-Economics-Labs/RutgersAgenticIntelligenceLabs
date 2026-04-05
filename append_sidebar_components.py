with open("packages/web/components/layout/Sidebar.tsx", "a") as f:
    f.write("""

const PROJECT_NAV_GROUPS = [
  {
    title: "Overview",
    items: [
      { href: "", label: "Overview", icon: LayoutDashboard },
    ],
  },
  {
    title: "Ontology",
    items: [
      { href: "/ontology/classes", label: "Classes", icon: Layers },
      { href: "/ontology/graph", label: "Graph", icon: Network },
      { href: "/ontology/schema", label: "Schema", icon: Database },
    ],
  },
  {
    title: "Data",
    items: [
      { href: "/sources", label: "Sources", icon: Database },
      { href: "/pipelines", label: "Pipelines", icon: GitBranch },
      { href: "/sql", label: "SQL", icon: Table2 },
    ],
  },
  {
    title: "Research",
    items: [
      { href: "/questions", label: "Questions", icon: MessageCircleQuestion },
      { href: "/agent", label: "Agent", icon: BotMessageSquare },
      { href: "/analysis", label: "Analysis", icon: BarChart2 },
    ],
  },
  {
    title: "Ops",
    items: [
      { href: "/jobs", label: "Jobs", icon: Activity },
      { href: "/quality", label: "Quality", icon: ShieldCheck },
      { href: "/context", label: "Context", icon: BookOpen },
    ],
  },
];

const SHARED_NAV_GROUPS = [
  {
    title: "Platform",
    items: [
      { href: "/registry", label: "Registry", icon: Library },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function ProjectSidebarContent({ projectSlug }: { projectSlug: string }) {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();

  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-[--border] bg-[--card] h-[calc(100vh-3rem)] sticky top-12">
      <nav className="flex-1 py-3 overflow-y-auto">
        <div className="mb-3">
          <Link
            href="/projects"
            className={cn(
              "flex items-center justify-between px-4 py-2.5 text-sm transition-colors group text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
            )}
          >
            <div className="flex items-center gap-3">
              <FolderOpen size={15} />
              All Projects
            </div>
          </Link>
        </div>

        {PROJECT_NAV_GROUPS.map((group) => (
          <div key={group.title} className="mb-3 last:mb-0">
            {group.title !== "Overview" && (
              <p className="px-4 py-1 text-[10px] text-[--muted-foreground] uppercase tracking-wide font-medium">
                {group.title}
              </p>
            )}
            <div className="mt-1">
              {group.items.map(({ href, label, icon: Icon }) => {
                const fullHref = `/${projectSlug}${href}`;
                const active = href === "" ? pathname === `/${projectSlug}` : pathname.startsWith(fullHref);

                return (
                  <Link
                    key={href}
                    href={fullHref}
                    className={cn(
                      "flex items-center justify-between px-4 py-2.5 text-sm transition-colors group",
                      active
                        ? "bg-[--accent]/20 text-[--primary] font-medium"
                        : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <Icon size={15} />
                      {label}
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}

        <div className="my-3 border-t border-[--border]" />

        {SHARED_NAV_GROUPS.map((group) => (
          <div key={group.title} className="mb-3 last:mb-0">
            <div className="mt-1">
              {group.items.map(({ href, label, icon: Icon }) => {
                const active = pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "flex items-center justify-between px-4 py-2.5 text-sm transition-colors group",
                      active
                        ? "bg-[--accent]/20 text-[--primary] font-medium"
                        : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <Icon size={15} />
                      {label}
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}

      </nav>
      <div className="px-4 py-3 border-t border-[--border] flex items-center justify-between">
        <p className="text-[10px] text-[--muted-foreground]">Rutgers Agentic Intelligence Labs</p>
        <button
          onClick={toggle}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          className="p-1.5 rounded text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted] transition-colors"
        >
          {theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
        </button>
      </div>
    </aside>
  );
}

export function ProjectSidebar({ projectSlug }: { projectSlug: string }) {
  return (
    <Suspense fallback={<aside className="w-56 shrink-0 flex flex-col border-r border-[--border] bg-[--card] h-[calc(100vh-3rem)] sticky top-12" />}>
      <ProjectSidebarContent projectSlug={projectSlug} />
    </Suspense>
  );
}
""")
