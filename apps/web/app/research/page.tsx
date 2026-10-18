"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";
import { num, pct, tone } from "@/lib/format";

type Candle = { date: string; open: number; high: number; low: number; close: number };

function Research() {
  const params = useSearchParams();
  const initial = params.get("symbol") || "RELIANCE";
  const exchange = (params.get("exchange") || "NSE").toUpperCase();
  const [symbol, setSymbol] = useState(initial);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ symbol: string; name?: string | null; exchange: string }[]>([]);
  const [quote, setQuote] = useState<Record<string, unknown> | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [error, setError] = useState("");
  const box = useRef<HTMLDivElement>(null);

  async function load(next = symbol, venue = exchange) {
    setError("");
    try {
      const [q, c] = await Promise.all([
        api<{ quote: Record<string, unknown> }>(`/api/v1/market/quote?symbol=${encodeURIComponent(next)}&exchange=${encodeURIComponent(venue)}`),
        api<{ history: { candles?: Candle[]; error?: string } }>(`/api/v1/market/candles?symbol=${encodeURIComponent(next)}&exchange=${encodeURIComponent(venue)}&interval=1d`),
      ]);
      setQuote(q.quote);
      setCandles(c.history.candles || []);
      if (c.history.error) setError(c.history.error);
    } catch (err) {
      setQuote(null);
      setCandles([]);
      setError(err instanceof Error ? err.message : "Lookup failed");
    }
  }

  useEffect(() => { load(initial, exchange); }, [initial, exchange]);

  useEffect(() => {
    if (!box.current || candles.length === 0) return;
    let chart: { remove: () => void } | null = null;
    let active = true;
    import("lightweight-charts").then(({ createChart }) => {
      if (!active || !box.current) return;
      const instance = createChart(box.current, {
        height: 360,
        layout: { background: { color: "transparent" }, textColor: "#5E706A" },
        grid: { vertLines: { color: "#E3EAE7" }, horzLines: { color: "#E3EAE7" } },
        timeScale: { borderColor: "#E3EAE7" },
      });
      const series = instance.addCandlestickSeries({ upColor: "#00B386", downColor: "#D64545", borderVisible: false, wickUpColor: "#00B386", wickDownColor: "#D64545" });
      series.setData(candles.map((candle) => ({ time: candle.date.slice(0, 10), open: candle.open, high: candle.high, low: candle.low, close: candle.close })));
      instance.timeScale().fitContent();
      chart = instance;
    });
    return () => { active = false; chart?.remove(); };
  }, [candles]);

  const change = quote?.change_pct as number | undefined;

  return (
    <div className="grid gap-4">
      <section className="panel grid gap-3 p-4 md:grid-cols-[1fr_auto]">
        <input value={query} placeholder="Search NSE or BSE symbol" onChange={(event) => setQuery(event.target.value)} />
        <button type="button" onClick={async () => {
          const body = await api<{ results: { symbol: string; name?: string | null; exchange: string }[] }>(`/api/v1/market/search?q=${encodeURIComponent(query)}`);
          setHits(body.results);
        }}>Search</button>
      </section>
      {hits.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {hits.map((hit) => (
            <button key={`${hit.exchange}:${hit.symbol}`} className="ghost" type="button" onClick={() => { setSymbol(hit.symbol); load(hit.symbol, hit.exchange); }}>
              {hit.exchange}:{hit.symbol}
            </button>
          ))}
        </div>
      )}
      {error && <Failure error={error} onRetry={() => load()} />}
      {quote && (
        <section className="panel p-4">
          <h1 className="text-xl font-semibold">{String(quote.company || quote.symbol || symbol)}</h1>
          <p className={`font-mono text-3xl ${tone(change)}`}>{num(quote.price as number)} <span className="text-lg">{pct(change)}</span></p>
          <p className="text-xs text-mute">Source {String(quote.provider)} · as of {String(quote.market_time || "unknown")} · {quote.quote_stale ? "stale" : "quote timestamp accepted"} · unofficial feed</p>
        </section>
      )}
      <div ref={box} className="panel p-2" />
      {candles.length === 0 && <p className="text-sm text-mute">No daily candles to draw.</p>}
    </div>
  );
}

export default function ResearchPage() {
  return (
    <Suspense fallback={<p>Loading research…</p>}>
      <Research />
    </Suspense>
  );
}
