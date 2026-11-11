import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { ApiKeyProvider } from "@/state/ApiKeyContext";
import { AppShell } from "@/components/AppShell";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Golf Coach",
  description: "Camera-based golf swing analysis and coaching.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ApiKeyProvider>
          <AppShell>{children}</AppShell>
        </ApiKeyProvider>
      </body>
    </html>
  );
}
