import type { Metadata } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";
import { ConvexClientProvider } from "./convex-provider";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Suspense } from "react";

export const metadata: Metadata = {
  title: "RAIL — Rutgers Agentic Intelligence Labs",
  description: "Open data and ontology platform",
};

import { Toaster } from "sonner";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <ConvexClientProvider>
          <ThemeProvider>
            <Suspense fallback={<div className="flex h-screen items-center justify-center">Loading...</div>}>
              {children}
            </Suspense>
            <Toaster richColors position="bottom-right" />
          </ThemeProvider>
        </ConvexClientProvider>
      </body>
    </html>
  );
}
