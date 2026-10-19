"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Failure, Loading } from "@/components/States";
import { api, token } from "@/lib/api";
import { num, tone } from "@/lib/format";
import { listedLogoUrl } from "@/lib/logos";

type Quote = {
  display_symbol?: string;
  name?: string;
  company?: string;
  price?: number;
  change?: number | null;
  change_pct?: number | null;
  currency?: string;
  exchange?: string;
  market_time?: string;
  quote_stale?: boolean;
  error?: string;
  provider?: string;
  sector?: string;
  sparkline?: number[];
};

type Dashboard = {
  session: { label: string; limitation: string; as_of: string; state?: string };
  indices: Quote[];
  breadth: { advances: number; declines: number; unchanged: number; sample: number; missing: number; advance_ratio: number | null };
  heatmap: { sector: string; change_pct: number; count: number }[];
  gainers: Quote[];
  losers: Quote[];
  approaching_52w_provider: { symbol: string; company?: string; price: number; distance_from_high_pct: number; distance_from_low_pct: number; method: string }[];
  failures: { symbol: string; error: string }[];
  universe_note: string;
  meta: { data_mode: string; fetched_at: string; delayed: boolean };
};

const SHORTCUTS = [
  { href: "/scanner", title: "Breakout scanner", hint: "Close-through setups", color: "#00B386", mark: "↗" },
  { href: "/highs", title: "52-week study", hint: "252 prior sessions", color: "#6C5CE7", mark: "▣" },
  { href: "/results", title: "Corporate Result", hint: "Upcoming company results", color: "#0EA5A0", mark: "▤" },
  { href: "/portfolio", title: "Your book", hint: "Watchlist and holdings", color: "#3B82F6", mark: "◎" },
];

const AVATAR_COLORS = ["#6C5CE7", "#5B6CFF", "#F5A524", "#E67E22", "#00B386", "#0EA5A0", "#8B5CF6", "#EC4899"];

export default function OverviewPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const inflight = useRef(false);
  const pulsing = useRef(false);

  const load = useCallback((background = false) => {
    if (!token()) {
      setLoading(false);
      setError("Sign in to load the market board.");
      return;
    }
    if (background && inflight.current) return;
    inflight.current = true;
    if (!background) {
      setLoading(true);
      setError("");
    }
    api<Dashboard>("/api/v1/market/dashboard")
      .then((body) => {
        setData(body);
        setError("");
      })
      .catch((err: Error) => {
        if (!background) setError(err.message);
      })
      .finally(() => {
        inflight.current = false;
        if (!background) setLoading(false);
      });
  }, []);

  const pulse = useCallback(() => {
    if (!token() || pulsing.current || document.visibilityState === "hidden") return;
    pulsing.current = true;
    api<{ indices: Quote[]; meta: Dashboard["meta"] }>("/api/v1/market/pulse")
      .then((body) => {
        setData((current) => current ? { ...current, indices: body.indices, meta: { ...current.meta, fetched_at: body.meta.fetched_at } } : current);
      })
      .catch(() => undefined)
      .finally(() => {
        pulsing.current = false;
      });
  }, []);

  useEffect(() => {
    load(false);
    const quotesTimer = window.setInterval(pulse, 5000);
    const boardTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") load(true);
    }, 8000);
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        pulse();
        load(true);
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(quotesTimer);
      window.clearInterval(boardTimer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, pulse]);

  if (loading) return <Loading label="Fetching index and NIFTY 50 quotes" />;
  if (error) return <Failure error={error} onRetry={load} />;
  if (!data) return null;

  const breadthTotal = data.breadth.advances + data.breadth.declines + data.breadth.unchanged || 1;

  return (
    <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
      <div className="grid min-w-0 gap-5">
        <div className="grid items-start gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <div className="text-xs font-semibold tracking-[0.14em] text-mute">{sessionEyebrow(data.session)}</div>
            <h1 className="mt-1 text-2xl font-semibold">{data.session.label}</h1>
            <p className="mt-1 max-w-xl text-sm text-mute">{data.session.limitation}</p>
          </div>
          <div className="grid justify-items-start gap-0.5 text-sm text-mute md:justify-items-end md:text-right">
            <div>{data.meta.delayed ? "Delayed unofficial feed" : "Demo feed"} · {data.meta.data_mode}</div>
            <div>Updated {new Date(data.meta.fetched_at).toLocaleTimeString("en-IN")}</div>
            <div>Quotes refresh in the background</div>
            <button className="ghost mt-2 w-fit" type="button" onClick={() => load(true)}>Refresh</button>
          </div>
        </div>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Index</h2>
            <Link href="/indices" className="pill">SCREENER</Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.indices.map((row) => (
              <IndexCard key={row.display_symbol} row={row} />
            ))}
          </div>
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Stocks moving</h2>
            <Link href="/scanner" className="pill">MOVERS</Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {data.gainers.slice(0, 4).map((row) => (
              <StockCard key={row.display_symbol} row={row} />
            ))}
          </div>
          {data.gainers.length === 0 && <p className="text-sm text-mute">No priced gainers in this sample.</p>}
          {data.losers.length > 0 && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {data.losers.slice(0, 4).map((row) => (
                <StockCard key={row.display_symbol} row={row} />
              ))}
            </div>
          )}
        </section>

        <section className="panel p-4">
          <h2 className="font-semibold">Sector heatmap</h2>
          <p className="text-xs text-mute">Equal average of available NIFTY 50 snapshot names. Missing quotes are excluded.</p>
          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-3">
            {data.heatmap.map((cell) => (
              <div key={cell.sector} className="rounded-xl p-3" style={heatStyle(cell.change_pct)}>
                <div className="text-sm font-medium">{cell.sector}</div>
                <div className={`mt-1 text-base font-semibold ${tone(cell.change_pct)}`}>{signedPct(cell.change_pct)}</div>
                <div className="text-xs text-mute">{cell.count} names</div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel p-4">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <h2 className="font-semibold">Breadth</h2>
            <div className="text-sm text-mute">
              {data.breadth.advances} up · {data.breadth.declines} down · {data.breadth.unchanged} flat
            </div>
          </div>
          <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-[var(--surface)]">
            <div style={{ width: `${(data.breadth.advances / breadthTotal) * 100}%`, background: "#00B386" }} />
            <div style={{ width: `${(data.breadth.unchanged / breadthTotal) * 100}%`, background: "#C5D1CC" }} />
            <div style={{ width: `${(data.breadth.declines / breadthTotal) * 100}%`, background: "#D64545" }} />
          </div>
          <p className="mt-3 text-sm text-mute">
            Sample {data.breadth.sample}. Missing {data.breadth.missing}. Advance ratio {data.breadth.advance_ratio ?? "—"}.
          </p>
          <p className="mt-2 text-xs text-mute">{data.universe_note}</p>
        </section>

        <section className="panel p-4">
          <h2 className="font-semibold">Near the provider 52-week high or low</h2>
          <p className="text-xs text-mute">This strip uses Yahoo&apos;s fiftyTwoWeek fields. The Highs page recomputes 252 prior sessions.</p>
          {data.approaching_52w_provider.length === 0 ? (
            <p className="mt-3 text-sm text-mute">None of the quotes that arrived are within 2% of the provider&apos;s 52-week high or low.</p>
          ) : (
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data.approaching_52w_provider.map((row) => (
                <article key={row.symbol} className="rounded-xl border border-[var(--line)] p-3">
                  <div className="font-medium">{row.symbol}</div>
                  <div className="text-xs text-mute">{row.company}</div>
                  <div className="mt-2 text-lg font-semibold">{inr(row.price)}</div>
                  <div className="mt-1 text-xs text-mute">From high {signedPct(row.distance_from_high_pct)}</div>
                  <div className="text-xs text-mute">From low {signedPct(row.distance_from_low_pct)}</div>
                </article>
              ))}
            </div>
          )}
        </section>

        {data.failures.length > 0 && (
          <section className="panel p-4">
            <h2 className="font-semibold">Quotes that failed</h2>
            <ul className="mt-2 text-sm text-mute">
              {data.failures.map((row) => <li key={row.symbol}>{row.symbol}: {row.error}</li>)}
            </ul>
          </section>
        )}
      </div>

      <aside className="grid content-start gap-3">
        {SHORTCUTS.map((item) => (
          <Link key={item.href} href={item.href} className="panel lift flex items-center gap-3 p-4">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-lg text-white" style={{ background: item.color }}>
              {item.mark}
            </span>
            <span>
              <span className="block font-semibold">{item.title}</span>
              <span className="block text-sm text-mute">{item.hint}</span>
            </span>
          </Link>
        ))}
        <article className="panel p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Your book</h2>
            <Link href="/portfolio" className="grid h-8 w-8 place-items-center rounded-full text-white" style={{ background: "#00B386" }} aria-label="Open portfolio">↗</Link>
          </div>
          <p className="mt-2 text-sm text-mute">Watchlists, holdings, and paper positions stay on their own pages. This board does not invent a portfolio value.</p>
        </article>
      </aside>
    </div>
  );
}

function IndexCard({ row }: { row: Quote }) {
  const up = (row.change_pct ?? 0) >= 0;
  return (
    <Link href={`/options?index=${encodeURIComponent(row.display_symbol || "")}`} className="panel lift block p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-base font-semibold">{row.name || row.display_symbol}</div>
          <div className="text-xs text-mute">{row.exchange || "NSE"} · Option chain</div>
        </div>
        <Sparkline values={row.sparkline} up={up} />
      </div>
      {row.error || row.price == null ? (
        <div className="mt-3 text-sm text-down">Unavailable. {row.error || "No price."}</div>
      ) : (
        <>
          <div className="mt-3 text-3xl font-bold tracking-tight">{inr(row.price)}</div>
          <div className={`mt-1 text-sm font-semibold ${tone(row.change_pct)}`}>{indexMove(row)}</div>
        </>
      )}
    </Link>
  );
}

function StockCard({ row }: { row: Quote }) {
  const label = row.company || row.display_symbol || "?";
  return (
    <article className="panel lift p-4">
      <CompanyLogo symbol={row.display_symbol} label={label} />
      <div className="mt-3 line-clamp-2 min-h-10 text-sm font-medium">{label}</div>
      <div className="mt-2 text-lg font-semibold">{inr(row.price)}</div>
      <div className={`text-sm font-semibold ${tone(row.change_pct)}`}>{moveLabel(row)}</div>
    </article>
  );
}

function CompanyLogo({ symbol, label }: { symbol?: string; label: string }) {
  const [failed, setFailed] = useState(false);
  const src = symbol && !failed ? listedLogoUrl(symbol) : "";
  if (!src) return <Avatar label={label} />;
  return (
    <span className="grid h-11 w-11 place-items-center overflow-hidden rounded-2xl border border-[var(--line)] bg-white">
      <img src={src} alt="" className="h-8 w-8 object-contain" onError={() => setFailed(true)} />
    </span>
  );
}

function Avatar({ label }: { label: string }) {
  let hash = 0;
  for (const ch of label) hash = (hash + ch.charCodeAt(0)) % AVATAR_COLORS.length;
  const letter = label.replace(/[^A-Za-z0-9]/g, "").slice(0, 1).toUpperCase() || "?";
  return (
    <span className="grid h-11 w-11 place-items-center rounded-2xl text-base font-semibold text-white" style={{ background: AVATAR_COLORS[hash] }}>
      {letter}
    </span>
  );
}

function Sparkline({ values, up }: { values?: number[]; up: boolean }) {
  if (!values || values.length < 2) return <div className="h-8 w-[76px]" />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 76;
  const height = 32;
  const d = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 6) - 3;
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={d} fill="none" stroke={up ? "#00B386" : "#D64545"} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function sessionEyebrow(session: Dashboard["session"]) {
  const label = session.label.toLowerCase();
  if (label.includes("weekend") || label.includes("closed") || session.state === "closed") return "MARKET CLOSED";
  if (label.includes("pre-open") || session.state === "pre_open") return "PRE-OPEN · OPENS AT 09:15 AM";
  return "MARKET CLOSES AT 03:30 PM";
}

function inr(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `₹${num(value)}`;
}

function signedPct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function indexMove(row: Quote) {
  if (row.change == null && row.change_pct == null) return "—";
  const amount = row.change == null ? "" : num(Math.abs(row.change));
  const percent = row.change_pct == null ? "" : `(${row.change_pct > 0 ? "+" : row.change_pct < 0 ? "-" : ""}${Math.abs(row.change_pct).toFixed(2)}%)`;
  if (amount && percent) return `${amount} ${percent}`;
  return amount || percent;
}

function moveLabel(row: Quote) {
  if (row.change == null && row.change_pct == null) return "—";
  const amount = row.change == null ? "" : num(Math.abs(row.change));
  const percent = row.change_pct == null ? "" : `${Math.abs(row.change_pct).toFixed(2)}%`;
  if (amount && percent) return `${amount} (${percent})`;
  return amount || percent;
}

function heatStyle(value: number): React.CSSProperties {
  const strength = Math.min(Math.abs(value) / 1.5, 1);
  const rgb = value >= 0 ? "0, 179, 134" : "214, 69, 69";
  return { background: `rgba(${rgb}, ${0.12 + strength * 0.38})` };
}
