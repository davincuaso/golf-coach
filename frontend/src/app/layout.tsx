import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { LegacySettingsCleanup } from "@/components/LegacySettingsCleanup";
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
        <LegacySettingsCleanup />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
