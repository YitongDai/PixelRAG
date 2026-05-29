"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

const links = [
  { href: "/", label: "Search" },
  { href: "/chat", label: "Agent" },
  { href: "/docs", label: "API Docs" },
  { href: "/status", label: "Status" },
]

export function NavLinks() {
  const pathname = usePathname()

  return (
    <div className="flex items-center gap-6">
      {links.map(({ href, label }) => {
        const isActive =
          href === "/" ? pathname === "/" : pathname.startsWith(href)
        return (
          <Link
            key={href}
            href={href}
            className={`text-sm transition-colors hover:text-foreground ${
              isActive
                ? "nav-link-active text-foreground"
                : "text-muted-foreground"
            }`}
          >
            {label}
          </Link>
        )
      })}
    </div>
  )
}
