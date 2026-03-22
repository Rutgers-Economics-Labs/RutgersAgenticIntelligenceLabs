import type { Metadata } from "next";
import "./globals.css";
import { ConvexClientProvider } from "./convex-provider";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "RAIL — Rutgers Agentic Intelligence Labs",
  description: "Open data and ontology platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <ConvexClientProvider>
          <ThemeProvider>{children}</ThemeProvider>
        </ConvexClientProvider>
      </body>
    </html>
  );
}
