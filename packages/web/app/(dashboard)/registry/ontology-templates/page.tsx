"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function OntologyTemplatesPage() {
  const templates = useQuery(api.ontologyTemplates.list) || [];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {templates.map((template) => (
        <Card key={template._id} className="flex flex-col">
          <CardHeader>
            <div className="flex justify-between items-start">
              <div>
                <CardTitle className="text-lg">{template.name}</CardTitle>
                <CardDescription className="font-mono text-xs mt-1 text-muted-foreground">{template.slug}</CardDescription>
              </div>
              <Badge variant="outline" className="text-xs">{template.version}</Badge>
            </div>
          </CardHeader>
          <CardContent className="flex-1">
            <p className="text-sm text-muted-foreground mb-4">
              {template.description}
            </p>
            <div className="flex flex-wrap gap-2">
              {template.tags?.map((tag) => (
                <Badge key={tag} variant="secondary" className="text-xs">
                  {tag}
                </Badge>
              ))}
            </div>
          </CardContent>
          <CardFooter className="border-t border-border pt-4">
            <Button variant="outline" size="sm" className="w-full gap-2">
              View Template
              <ExternalLink className="h-4 w-4" />
            </Button>
          </CardFooter>
        </Card>
      ))}

      {templates.length === 0 && (
        <div className="col-span-full py-12 text-center text-muted-foreground">
          No ontology templates found. Seed the database to get started.
        </div>
      )}
    </div>
  );
}