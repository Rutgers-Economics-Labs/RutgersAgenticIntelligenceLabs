import "@/app/globals.css";
import "katex/dist/katex.min.css";
import type { Metadata } from "next";
import { ReactNode } from "react";

export const metadata: Metadata = {
  title: "RAIL Command Center",
  description: "Planner-first command center for RAIL projects",
  icons: {
    apple: "/rel-logo.jpeg"
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function () {
                try {
                  var theme = localStorage.getItem('rail-theme') || 'light';
                  document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
                } catch (e) {
                  document.documentElement.dataset.theme = 'light';
                }
              })();
            `
          }}
        />
        {children}
      </body>
    </html>
  );
}
