"use client";

import { useState } from "react";
import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { Failure, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { num, pct } from "@/lib/format";

type Hit = {
  symbol: string;
  company?: string;
  close?: number;
  relative_volume?: number;
  level?: number;
  confirmation?: string;
  bar_time?: string;
  triggered: string[];
  invalidation?: string;
  indicators: { rsi?: number | null; sma?: number | null; macd_histogram?: number | null };
  chart: string;
};

export default function ScannerPage() {
  const [lookback, setLookback] = useState(20);
  const [relative, setRelative] = useState(2);
  const [direction, setDirection] = useState("breakout");
  const [interval, setInterval] = useState("1d");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ qualified: Hit[]; scanned: number; example_only: string; rejected: number } | null>(null);

  async function run() {
    setLoading(true);
    setError("");
    try {
      const body = await api<{ qualified: Hit[]; scanned: number; example_only: string; rejected: number }>("/api/v1/scanner/run", {
        method: "POST",
        body: JSON.stringify({
          interval,
          rules: {
            direction,
            lookback,
            min_relative_volume: relative,
            min_avg_traded_value: 50000000,
            require_above_sma: 50,
            require_close_through: true,
          },
        }),
      });
      setResult(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-4">
      <PageHead
        kicker="Market"
        title="Breakout scanner"
        lede="A close through the prior lookback high, with relative volume and a liquidity floor, is a filter. It is not a forecast. Intraday scans need a Pro plan. Free plans are limited to daily bars."
      />
      <section className="panel grid gap-3 p-4 md:grid-cols-4">
        <label className="grid gap-1 text-sm">Direction
          <select value={direction} onChange={(event) => setDirection(event.target.value)}>
            <option value="breakout">Breakout</option>
            <option value="breakdown">Breakdown</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm">Lookback
          <input type="number" value={lookback} min={2} max={250} onChange={(event) => setLookback(Number(event.target.value))} />
        </label>
        <label className="grid gap-1 text-sm">Min relative volume
          <input type="number" value={relative} step="0.1" onChange={(event) => setRelative(Number(event.target.value))} />
        </label>
        <label className="grid gap-1 text-sm">Timeframe
          <select value={interval} onChange={(event) => setInterval(event.target.value)}>
            {["1d", "1h", "30m", "15m", "5m", "1m"].map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <button type="button" onClick={run}>Run scan</button>
      </section>
      {loading && <Loading label="Scanning the NIFTY 50 snapshot" />}
      {error && <Failure error={error} onRetry={run} />}
      {result && (
        <section className="panel overflow-x-auto p-4">
          <h2>{result.qualified.length} qualified of {result.scanned}</h2>
          <p className="text-sm text-mute">{result.rejected} did not qualify or had no data.</p>
          <p className="text-sm text-mute">{result.example_only}</p>
          {result.qualified.length === 0 ? <p className="mt-4 text-sm">No names met every condition on the latest bar.</p> : (
            <table className="mt-3">
              <thead><tr><th>Symbol</th><th>Last</th><th>Level</th><th>Rel vol</th><th>Bar</th><th>Why</th></tr></thead>
              <tbody>
                {result.qualified.map((row) => (
                  <tr key={row.symbol}>
                    <td><Link href={row.chart}>{row.symbol}</Link><div className="text-xs text-mute">{row.company}</div></td>
                    <td className="font-mono">{num(row.close)}</td>
                    <td className="font-mono">{num(row.level)}<div className="text-xs text-mute">{row.confirmation}</div></td>
                    <td className="font-mono">{row.relative_volume ?? "—"}</td>
                    <td className="text-xs">{row.bar_time}<div>RSI {row.indicators.rsi ?? "—"}</div></td>
                    <td className="text-xs">{row.triggered.join(" ")} {row.invalidation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
