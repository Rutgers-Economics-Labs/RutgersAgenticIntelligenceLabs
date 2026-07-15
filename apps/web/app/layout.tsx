import "@/app/globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";

export const metadata: Metadata = {
  title: "RAIL · KRAIL platform",
  description: "Visual control plane for KRAIL knowledge and workflows",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
    apple: "/rel-logo.jpeg"
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
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
