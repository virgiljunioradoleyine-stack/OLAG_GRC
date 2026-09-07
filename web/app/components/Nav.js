"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconBell, IconChart, IconDoc, IconHome, IconInfo, IconLogo, IconMap,
} from "./Icons";

const ITEMS = [
  { href: "/", label: "Overview", Icon: IconHome },
  { href: "/map", label: "Live Map", Icon: IconMap },
  { href: "/trends", label: "Data & Trends", Icon: IconChart },
  { href: "/alerts", label: "Alerts", Icon: IconBell, badge: true },
  { href: "/reports", label: "Reports", Icon: IconDoc },
  { href: "/about", label: "About", Icon: IconInfo },
];

export default function Nav({ activeAlerts = 0 }) {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark"><IconLogo /></span>
        <span>
          <span className="brand-name">Pra River Watch</span>
          <span className="brand-tag">Cleaner Rivers, Safer Communities</span>
        </span>
      </div>
      <nav className="nav" aria-label="Main">
        {ITEMS.map(({ href, label, Icon, badge }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} aria-current={active ? "page" : undefined}>
              <Icon />
              <span>{label}</span>
              {badge && activeAlerts > 0 && (
                <span className="count" aria-label={`${activeAlerts} alerts active now`}>
                  {activeAlerts}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        Satellite monitoring for the Pra basin, Ghana.
      </div>
    </aside>
  );
}
