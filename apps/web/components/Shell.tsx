"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL, api, setToken, token } from "@/lib/api";
import { TopSearch } from "@/components/TopSearch";

const GROUPS = [
  {
    label: "Market",
    links: [
      ["/", "Market Overview", "board"],
      ["/scanner", "Breakout Scanner", "scan"],
      ["/indices", "Index Intelligence", "index"],
      ["/highs", "52-Week Highs/Lows", "range"],
      ["/results", "Corporate Result", "result"],
    ],
  },
  {
    label: "Research",
    links: [
      ["/research", "Stock Research", "search"],
      ["/assistant", "AI Assistant", "spark"],
      ["/strategies", "Strategy Lab", "lab"],
    ],
  },
  {
    label: "Trading",
    links: [
      ["/paper", "Paper Trading", "paper"],
      ["/portfolio", "Watchlists & Portfolio", "book"],
      ["/alerts", "Alerts", "bell"],
    ],
  },
  {
    label: "Account",
    links: [
      ["/profile", "Profile", "user"],
      ["/settings", "Settings", "gear"],
      ["/status", "Data status", "pulse"],
    ],
  },
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [mode, setMode] = useState("live");
  const [open, setOpen] = useState(false);
  const [authed, setAuthed] = useState(false);
  const authScreen = path === "/login" || path === "/register";

  useEffect(() => {
    setAuthed(Boolean(token()));
    setOpen(false);
    const saved = localStorage.getItem("bazaar_theme");
    if (saved) document.documentElement.dataset.theme = saved;
    api<{ data_mode: string }>("/api/v1/health")
      .then((body) => setMode(body.data_mode))
      .catch(() => setMode("unreachable"));
  }, [path]);

  if (authScreen) {
    return (
      <div className="grid min-h-screen place-items-center px-4 py-10">
        <div className="w-full max-w-md">
          <Brand />
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      {open && <button className="app-backdrop lg:hidden" type="button" aria-label="Close menu" onClick={() => setOpen(false)} />}
      <aside className={`app-nav${open ? " is-open" : ""}`}>
        <Brand />
        <nav className="grid gap-0.5">
          {GROUPS.map((group) => (
            <div key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.links.map(([href, label, icon]) => {
                const active = href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
                return (
                  <Link key={href} href={href} data-active={active} className="nav-link" onClick={() => setOpen(false)}>
                    <NavIcon name={icon} />
                    {label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="mt-4 px-2 sm:hidden">
          <AccountAction authed={authed} onSignOut={() => { setToken(null); setOpen(false); router.push("/login"); }} />
        </div>
      </aside>
      <div className="min-w-0">
        {mode === "demo" && (
          <div className="banner">Demo mode. Every price on this screen is synthetic and is not a market quote.</div>
        )}
        {mode === "unreachable" && (
          <div className="banner">The market API{API_URL ? ` at ${API_URL}` : ""} is not responding. Market figures are hidden until it is back.</div>
        )}
        <header className="app-top">
          <button className="ghost lg:hidden" onClick={() => setOpen(true)} type="button" aria-label="Open menu">Menu</button>
          <TopSearch />
          <div className="hidden shrink-0 sm:block">
            <AccountAction authed={authed} onSignOut={() => { setToken(null); router.push("/login"); }} />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1440px] p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}

function AccountAction({ authed, onSignOut }: { authed: boolean; onSignOut: () => void }) {
  if (authed) {
    return (
      <button className="ghost" type="button" onClick={onSignOut}>Sign out</button>
    );
  }
  return <Link href="/login" className="sign-chip">Sign in</Link>;
}

function Brand() {
  return (
    <Link href="/" className="brand">
      <img src="/stoxs8-mark.svg" alt="" width={36} height={36} className="h-9 w-9" />
      <span>
        <strong>Stoxs8</strong>
        Indian markets
      </span>
    </Link>
  );
}

function NavIcon({ name }: { name: string }) {
  const common = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", "aria-hidden": true as const };
  if (name === "board") {
    return (
      <svg {...common}>
        <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
        <rect x="9" y="1.5" width="5.5" height="5.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
        <rect x="1.5" y="9" width="5.5" height="5.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
        <rect x="9" y="9" width="5.5" height="5.5" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  }
  if (name === "scan") {
    return (
      <svg {...common}>
        <path d="M2 11.5 6 7.5l2.2 2.2L14 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M10 4h4v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "index") {
    return (
      <svg {...common}>
        <path d="M2 13V3M2 13h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M4.5 10.5 7 7l2 2 3-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (name === "range") {
    return (
      <svg {...common}>
        <path d="M3 4h10M3 8h10M3 12h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "result") {
    return (
      <svg {...common}>
        <rect x="2.5" y="2.5" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.4" />
        <path d="M5 5.5h6M5 8h6M5 10.5h3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "search") {
    return (
      <svg {...common}>
        <circle cx="7" cy="7" r="4.25" stroke="currentColor" strokeWidth="1.5" />
        <path d="M10.4 10.4 13.5 13.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "spark") {
    return (
      <svg {...common}>
        <path d="M8 1.8 9.2 6h4.3L10.2 8.6l1.2 4.1L8 10.2 4.6 12.7 5.8 8.6 2.5 6h4.3L8 1.8Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      </svg>
    );
  }
  if (name === "lab") {
    return (
      <svg {...common}>
        <path d="M6 2.5h4M6.8 2.5v4.2L3.2 13a1.4 1.4 0 0 0 1.2 2.1h7.2a1.4 1.4 0 0 0 1.2-2.1L9.2 6.7V2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (name === "paper") {
    return (
      <svg {...common}>
        <rect x="2.5" y="3" width="11" height="10" rx="1.6" stroke="currentColor" strokeWidth="1.4" />
        <path d="M5 7.2h6M5 9.6h3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "book") {
    return (
      <svg {...common}>
        <path d="M3 3.2h4.2A1.8 1.8 0 0 1 9 5v8.2H4.6A1.6 1.6 0 0 0 3 14.8V3.2Z" stroke="currentColor" strokeWidth="1.3" />
        <path d="M13 3.2H8.8A1.8 1.8 0 0 0 7 5v8.2h4.4A1.6 1.6 0 0 1 13 14.8V3.2Z" stroke="currentColor" strokeWidth="1.3" />
      </svg>
    );
  }
  if (name === "bell") {
    return (
      <svg {...common}>
        <path d="M8 2.4a3.6 3.6 0 0 0-3.6 3.6v2.1L3 10.6h10l-1.4-2.5V6A3.6 3.6 0 0 0 8 2.4Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        <path d="M6.6 11.2a1.4 1.4 0 0 0 2.8 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "user") {
    return (
      <svg {...common}>
        <circle cx="8" cy="5.5" r="2.2" stroke="currentColor" strokeWidth="1.4" />
        <path d="M3.2 13.2c.7-2.2 2.4-3.3 4.8-3.3s4.1 1.1 4.8 3.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "gear") {
    return (
      <svg {...common}>
        <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.4" />
        <path d="M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="8" cy="8" r="5.2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 5.2V8l1.8 1.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
