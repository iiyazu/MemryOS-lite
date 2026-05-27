"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const nav = [
  { href: "/observability", label: "Observability", tone: "accent" },
  { href: "/lane-audit", label: "Lane audit", tone: "warn" },
  { href: "/knowledge", label: "Knowledge explorer", tone: "ok" }
];

export function AppShell({ children, rail, context = "observability" }: { children: ReactNode; rail?: ReactNode; context?: string }) {
  const pathname = usePathname();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/">
          <span className="mark">x</span>
          <span>
            <strong>xmuse</strong>
            <span>{context}</span>
          </span>
        </Link>
        <div className="nav-label">Surfaces</div>
        {nav.map((item) => (
          <Link key={item.href} className={`nav-item ${pathname === item.href ? "active" : ""}`} href={item.href}>
            <span className={`dot ${item.tone}`} />
            {item.label}
          </Link>
        ))}
        <div className="nav-label">Backend</div>
        <div className="panel panel-pad stack">
          <span className="mono">POST /mcp</span>
          <span className="muted">JSON-RPC 2.0 · localhost:8100</span>
        </div>
      </aside>
      <main className="main">{children}</main>
      <aside className="right-rail rail-stack">{rail}</aside>
    </div>
  );
}
