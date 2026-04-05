"use client";

import { usePathname, useRouter } from "next/navigation";
import * as Tabs from "@radix-ui/react-tabs";

export default function RegistryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();

  const tabValue = pathname.includes("/registry/connectors")
    ? "connectors"
    : pathname.includes("/registry/ontology-templates")
    ? "ontology-templates"
    : "data-catalog";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Registry</h1>
        <p className="mt-1 text-sm text-muted-foreground max-w-2xl">
          Browse and manage templates and data sources.
        </p>
      </div>

      <Tabs.Root
        value={tabValue}
        onValueChange={(val) => {
          if (val === "data-catalog") router.push("/registry");
          else router.push(`/registry/${val}`);
        }}
      >
        <Tabs.List className="flex gap-4 border-b border-border mb-6">
          <Tabs.Trigger
            value="connectors"
            className="px-4 py-2 text-sm text-muted-foreground data-[state=active]:text-foreground data-[state=active]:border-b-2 data-[state=active]:border-primary hover:text-foreground transition-colors"
          >
            Connectors
          </Tabs.Trigger>
          <Tabs.Trigger
            value="ontology-templates"
            className="px-4 py-2 text-sm text-muted-foreground data-[state=active]:text-foreground data-[state=active]:border-b-2 data-[state=active]:border-primary hover:text-foreground transition-colors"
          >
            Ontology Templates
          </Tabs.Trigger>
          <Tabs.Trigger
            value="data-catalog"
            className="px-4 py-2 text-sm text-muted-foreground data-[state=active]:text-foreground data-[state=active]:border-b-2 data-[state=active]:border-primary hover:text-foreground transition-colors"
          >
            Data Catalog
          </Tabs.Trigger>
        </Tabs.List>
      </Tabs.Root>

      <div>{children}</div>
    </div>
  );
}
