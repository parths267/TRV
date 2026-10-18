"use client";

import { useState } from "react";
import Link from "next/link";
import { Failure, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { num, pct } from "@/lib/format";

type Row = {
  symbol: string;
  company?: string;
  close?: number;
  distance_from_high_pct?: number;
  distance_from_low_pct?: number;
  relative_volume?: number | null;
  sessions_used?: number;
  partial_history?: boolean;
  bar_time?: string;
  chart: string;
  volume_confirmed?: boolean;
};

const GROUPS = [
  ["new_closing_highs", "New closing highs"],
  ["new_intraday_highs", "Intraday highs, not a closing high"],
  ["approaching_highs", "Approaching the high"],
  ["new_closing_lows", "New closing lows"],
  ["new_intraday_lows", "Intraday lows, not a closing low"],
  ["approaching_lows", "Approaching the low"],
] as const;

export default function HighsPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<Record<string, Row[] | string> & { method?: string; unavailable?: { symbol: string; reason?: string }[] } | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setData(await api("/api/v1/highs?approach_pct=2"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Range study failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-4">
      <section className="panel p-4">
        <h1 className="text-xl font-semibold">52-week range</h1>
        <p className="text-sm text-mute">Calculated from prior daily sessions, up to 252, excluding the latest bar. A short history is marked partial. This is not Yahoo's precomputed 52-week field.</p>
        <button className="mt-3" type="button" onClick={load}>Calculate</button>
      </section>
      {loading && <Loading label="Loading two years of daily bars" />}
      {error && <Failure error={error} onRetry={load} />}
      {data && (
        <>
          <p className="text-sm text-mute">{data.method}</p>
          {GROUPS.map(([key, title]) => {
            const rows = (data[key] as Row[]) || [];
            return (
              <section key={key} className="panel p-4">
                <h2>{title}</h2>
                {rows.length === 0 ? <p className="text-sm text-mute">None in the latest bars.</p> : (
                  <table>
                    <thead><tr><th>Symbol</th><th>Close</th><th>From high</th><th>From low</th><th>Sessions</th></tr></thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.symbol}>
                          <td><Link href={row.chart}>{row.symbol}</Link><div className="text-xs text-mute">{row.company}</div></td>
                          <td className="font-mono">{num(row.close)}</td>
                          <td className="font-mono">{pct(row.distance_from_high_pct)}</td>
                          <td className="font-mono">{pct(row.distance_from_low_pct)}</td>
                          <td className="text-xs">{row.sessions_used}{row.partial_history ? " partial" : ""} · vol {row.relative_volume ?? "—"} · {row.bar_time}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}
