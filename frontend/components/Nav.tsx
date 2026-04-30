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
  const rawPath = usePathname();
  // trailingSlash:true 时静态导出路径带尾斜杠，去掉后再比较（保留根路径 /）
  const path = rawPath !== "/" && rawPath.endsWith("/") ? rawPath.slice(0, -1) : rawPath;

  return (
    <nav style={{
      background: "var(--surface)",
      borderBottom: "1px solid var(--border)",
      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    }}>
      <div className="max-w-6xl mx-auto px-6 flex items-center gap-2 h-16">
        <span className="font-black text-base tracking-[0.15em] shrink-0 mr-4" style={{ color: "var(--accent)" }}>
          REDBEACON
        </span>
        {links.map(l => {
          const active = path === l.href;
          return (
            <Link
              key={l.href}
              href={l.href}
              className="text-sm font-medium whitespace-nowrap px-4 py-1.5 rounded transition-colors shrink-0"
              style={{
                background: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--muted)",
              }}
            >
              {l.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
