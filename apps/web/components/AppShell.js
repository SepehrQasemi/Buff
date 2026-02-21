import Link from "next/link";
import { useRouter } from "next/router";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/runs", label: "Runs" },
  { href: "/experiments", label: "Experiments" },
  { href: "/help", label: "Help" },
];

const isActive = (pathname, href) => {
  const current = String(pathname || "");
  if (href === "/") {
    return current === "/";
  }
  if (href === "/runs") {
    return current === "/runs" || current.startsWith("/runs/");
  }
  if (href === "/experiments") {
    return current === "/experiments" || current.startsWith("/experiments/");
  }
  if (href === "/help") {
    return current === "/help" || current.startsWith("/help/");
  }
  return current === href;
};

export default function AppShell({ children, fullBleed = false }) {
  const router = useRouter();

  return (
    <div className={`app-shell ${fullBleed ? "app-shell-fullbleed" : ""}`} data-app-shell="true">
      <div className="app-shell-header">
        <nav className="app-shell-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => {
            const active = isActive(router.pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`app-shell-link ${active ? "active" : ""}`}
                aria-current={active ? "page" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className={`app-shell-content ${fullBleed ? "app-shell-content-fullbleed" : ""}`}>
        {children}
      </div>
    </div>
  );
}
