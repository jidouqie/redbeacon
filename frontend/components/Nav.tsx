"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/",           label: "总览"     },
  { href: "/login",      label: "账号管理" },
  { href: "/write",      label: "写文案"   },
  { href: "/automation", label: "自动化"   },
  { href: "/debug",      label: "指令调试" },
  { href: "/settings",   label: "设置"     },
];

export default function Nav() {
  const path = usePathname();

  const linkStyle = (href: string) => ({
    background: path === href ? "var(--accent)" : "transparent",
    color: path === href ? "#fff" : "var(--muted)",
  });

  return (
    <nav
      style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--surface)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
      }}
    >
      <div className="max-w-6xl mx-auto px-4 flex items-center gap-1 h-12 overflow-x-auto">
        <span className="font-semibold text-sm tracking-widest shrink-0 mr-3" style={{ color: "var(--accent)" }}>
          REDBEACON
        </span>
        {links.map(l => (
          <Link key={l.href} href={l.href}
            className="text-xs whitespace-nowrap px-2.5 py-1 rounded transition-colors shrink-0"
            style={linkStyle(l.href)}>
            {l.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
