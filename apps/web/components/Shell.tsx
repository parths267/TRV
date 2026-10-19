"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL, api, setToken, token } from "@/lib/api";
import { TopSearch } from "@/components/TopSearch";

const LINKS = [
  ["/", "Market Overview"],
  ["/scanner", "Breakout Scanner"],
  ["/indices", "Index Intelligence"],
  ["/highs", "52-Week Highs/Lows"],
  ["/results", "Corporate Result"],
  ["/research", "Stock Research"],
  ["/assistant", "AI Assistant"],
  ["/strategies", "Strategy Lab"],
  ["/paper", "Paper Trading"],
  ["/portfolio", "Watchlists & Portfolio"],
  ["/alerts", "Alerts"],
  ["/settings", "Settings"],
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [mode, setMode] = useState("live");
  const [open, setOpen] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(Boolean(token()));
    const saved = localStorage.getItem("bazaar_theme");
    if (saved) document.documentElement.dataset.theme = saved;
    api<{ data_mode: string }>("/api/v1/health")
      .then((body) => setMode(body.data_mode))
      .catch(() => setMode("unreachable"));
  }, [path]);

  return (
    <div className="min-h-screen">
      {mode === "demo" && (
        <div className="banner">Demo mode. Every price on this screen is synthetic and is not a market quote.</div>
      )}
      {mode === "unreachable" && (
        <div className="banner">The API at {API_URL} is not responding. Market figures are hidden until it is back.</div>
      )}
      <div className="lg:grid lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className={`${open ? "block" : "hidden"} lg:block min-w-0 overflow-hidden border-b lg:border-b-0 lg:border-r border-[var(--line)] bg-[var(--card)] p-4`}>
          <img src="/stoxs8.png" alt="Stoxs8" width={900} height={233} className="mb-5 h-auto w-full max-w-full" />
          <nav className="grid gap-1">
            {LINKS.map(([href, label]) => {
              const active = href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
              return (
                <Link key={href} href={href} data-active={active} className="nav-link" onClick={() => setOpen(false)}>
                  {label}
                </Link>
              );
            })}
            <Link href="/status" data-active={path === "/status"} className="nav-link">Data status</Link>
          </nav>
        </aside>
        <div className="min-w-0">
          <header className="relative z-40 flex items-center gap-3 border-b border-[var(--line)] bg-[var(--card)] px-4 py-3">
            <button className="ghost lg:hidden" onClick={() => setOpen((value) => !value)} type="button">Menu</button>
            <TopSearch />
            <div className="flex shrink-0 gap-2">
              {authed ? (
                <button
                  className="ghost"
                  type="button"
                  onClick={() => {
                    setToken(null);
                    router.push("/login");
                  }}
                >
                  Sign out
                </button>
              ) : (
                <Link href="/login" className="nav-link">Sign in</Link>
              )}
            </div>
          </header>
          <main className="p-4 md:p-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
