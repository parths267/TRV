"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHead } from "@/components/PageHead";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";
import { num, pct } from "@/lib/format";

type Screen = {
  id: string;
  title: string;
  summary: string;
  rule: string;
  status: string;
};

type Library = { strategies: { id: string; label: string }[]; limitations: string[]; costs: { round_trip_pct: number; engine_note: string } };
type Result = {
  error?: string;
  strategy_label?: string;
  total_return_pct?: number;
  win_rate_pct?: number;
  max_drawdown_pct?: number;
  sharpe_ratio?: number;
  profit_factor?: number;
  expectancy_pct?: number;
  buy_and_hold_return_pct?: number;
  total_trades?: number;
  disclaimer?: string;
  execution_note?: string;
  date_from?: string;
  date_to?: string;
};

const ACCENT: Record<string, string> = {
  high_momentum: "#00B386",
  volatility_contraction: "#6C5CE7",
  relative_strength: "#3B82F6",
  sector_rotation: "#F5A524",
  gap: "#E67E22",
  event: "#EC4899",
  volatility_breakout: "#0EA5A0",
  inside_daily: "#00B386",
  inside_15m: "#3DDC97",
  fii: "#8B5CF6",
  darvas: "#00B386",
  value: "#5B6CFF",
};

export default function StrategiesPage() {
  const [screens, setScreens] = useState<Screen[]>([]);
  const [error, setError] = useState("");
  const [library, setLibrary] = useState<Library | null>(null);
  const [symbol, setSymbol] = useState("RELIANCE");
  const [strategy, setStrategy] = useState("donchian");
  const [result, setResult] = useState<Result | null>(null);
  const [backtestError, setBacktestError] = useState("");

  useEffect(() => {
    api<{ screens: Screen[] }>("/api/v1/strategies/screens")
      .then((body) => setScreens(body.screens))
      .catch((err: Error) => setError(err.message));
    api<Library>("/api/v1/strategies/library").then(setLibrary).catch(() => setLibrary(null));
  }, []);

  return (
    <div className="grid gap-5">
      <PageHead
        kicker="Research"
        title="Strategy lab"
        lede="Pick a screen to see which index constituents meet it, across large, mid, and small caps. A match is a filter on delayed daily bars, not a recommendation."
      />
      {error && <Failure error={error} />}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {screens.map((item, index) => (
          <Link key={item.id} href={`/strategies/${item.id}`} className="panel lift flex gap-3 p-4">
            <span
              className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-sm font-bold text-white"
              style={{ background: ACCENT[item.id] || "#00B386" }}
            >
              {index + 1}
            </span>
            <span className="min-w-0">
              <span className="block font-semibold">{item.title}</span>
              <span className="mt-1 block text-sm text-mute">{item.summary}</span>
              <span className="mt-2 block text-xs text-[var(--text)]">{item.rule}</span>
            </span>
          </Link>
        ))}
      </div>

      <section className="panel p-4">
        <h2 className="font-semibold">Single-symbol backtest</h2>
        <p className="mt-1 text-sm text-mute">
          Runs the tradingview-mcp backtest with an approximate NSE delivery cost. A strong history is not a promise of profit.
          {library ? ` Round trip about ${library.costs.round_trip_pct.toFixed(3)}%.` : ""}
        </p>
        <form
          className="mt-3 flex flex-wrap gap-3"
          onSubmit={async (event) => {
            event.preventDefault();
            setBacktestError("");
            try {
              setResult(await api("/api/v1/strategies/backtest", {
                method: "POST",
                body: JSON.stringify({ symbol, strategy, period: "1y", initial_capital: 1000000 }),
              }));
            } catch (err) {
              setResult(null);
              setBacktestError(err instanceof Error ? err.message : "Backtest failed");
            }
          }}
        >
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} aria-label="Symbol" />
          <select value={strategy} onChange={(event) => setStrategy(event.target.value)} aria-label="Backtest strategy">
            {(library?.strategies || [{ id: "donchian", label: "Donchian" }]).map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
          <button type="submit">Backtest</button>
        </form>
        {backtestError && <p className="mt-3 text-sm text-down">{backtestError}</p>}
        {result && !result.error && (
          <div className="mt-4">
            <h3 className="font-medium">{result.strategy_label}</h3>
            <p className="font-mono text-2xl">{pct(result.total_return_pct)}</p>
            <p className="text-sm">Win rate {pct(result.win_rate_pct)} · max drawdown {pct(result.max_drawdown_pct)} · Sharpe {num(result.sharpe_ratio)} · profit factor {num(result.profit_factor)} · expectancy {pct(result.expectancy_pct)}</p>
            <p className="text-sm">Buy and hold {pct(result.buy_and_hold_return_pct)} · trades {result.total_trades} · {result.date_from} to {result.date_to}</p>
            <p className="mt-2 text-xs text-mute">{result.execution_note}</p>
            <p className="text-xs text-mute">{result.disclaimer}</p>
          </div>
        )}
        {result?.error && <p className="mt-3 text-sm">{result.error}</p>}
      </section>
    </div>
  );
}
