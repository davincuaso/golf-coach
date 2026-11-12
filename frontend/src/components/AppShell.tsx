"use client";
import { usePathname } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="Golf Coach home">
          <span className="brand-mark">
            <Icon name="flag" width={24} height={24} />
          </span>
          <span>
            golf<span className="font-normal">coach</span>
            <span className="brand-caption">YOUR PRACTICE PARTNER</span>
          </span>
        </Link>
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Main navigation" className="main-nav">
          <Link
            href="/"
            className={`nav-link ${pathname === "/" ? "active" : ""}`}
          >
            <Icon name="grid" />
            Swing Lab
            <Icon name="arrow" className="nav-arrow" width={15} />
          </Link>
          <Link
            href="/sessions"
            className={`nav-link ${pathname === "/sessions" ? "active" : ""}`}
          >
            <Icon name="camera" />
            Sessions
          </Link>
        </nav>
        <div className="sidebar-bottom">
          <span className="mini-golf-mark" aria-hidden="true">
            ◌
          </span>
          <p>
            Small adjustments.
            <br />
            Better swings.
          </p>
          <span className="text-xs text-[var(--muted)]">
            One thoughtful practice at a time.
          </span>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <span className="text-sm text-[var(--muted)]">
            Your personal practice workspace
          </span>
          <span className="status-pill status-green">
            <Icon name="spark" width={14} height={14} />
            ChatGPT prompt workflow
          </span>
        </header>
        <main id="main-content" className="page-content">
          {children}
        </main>
        <footer className="app-footer">
          <span>Made for a more intentional practice.</span>
          <span>2D video analysis · Your swing, your perspective</span>
        </footer>
      </div>
    </div>
  );
}
