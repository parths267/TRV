"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHead } from "@/components/PageHead";
import { Failure, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";

type Move = { triggered?: boolean; available?: boolean; change_pct?: number; reason?: string; from?: string; to?: string; confirmation?: string };
type Reading = { id: string; name: string; move: Move; gap: { available?: boolean; gap_pct?: number; reason?: string }; vwap: { value?: number | null; above?: boolean | null; note?: string } | null; intraday_error?: string; intraday_count?: number };

export default function IndicesPage() {
  const [threshold, setThreshold] = useState(-0.6);
  const [windowMinutes, setWindowMinutes] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<{
    example_rule: { statement: string; triggered: boolean };
    indices: Reading[];
    limitations: string[];
    banking_support: { breaks: number; unknown: number; universe_note: string };
    nifty50_breadth: { advance_ratio: number | null; advances: number; declines: number };
  } | null>(null);

  async function run() {
    setLoading(true);
    setError("");
    try {
      setData(await api("/api/v1/indices/monitor", {
        method: "POST",
        body: JSON.stringify({ threshold_pct: threshold, window_minutes: windowMinutes }),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Index study failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-4">
      <PageHead
        kicker="Market"
        title="Index intelligence"
        lede="Measure a short window on the main indices, then read breadth and the example rule. This is a study of delayed bars, not a signal to trade."
      />
      <section className="panel flex flex-wrap items-end gap-3 p-4">
        <label className="grid gap-1 text-sm">Threshold %
          <input type="number" step="0.1" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
        </label>
        <label className="grid gap-1 text-sm">Window minutes
          <input type="number" step="5" value={windowMinutes} onChange={(event) => setWindowMinutes(Number(event.target.value))} />
        </label>
        <button type="button" onClick={run}>Measure</button>
      </section>
      {loading && <Loading label="Reading 5-minute index bars" />}
      {error && <Failure error={error} onRetry={run} />}
      {data && (
        <>
          <section className="panel p-4">
            <h2>Example rule {data.example_rule.triggered ? "triggered" : "not triggered"}</h2>
            <p className="text-sm text-mute">{data.example_rule.statement}</p>
            <p className="mt-2 text-sm">Banking names below the prior 20-session low: {data.banking_support.breaks}. Unknown: {data.banking_support.unknown}. {data.banking_support.universe_note}</p>
            <p className="text-sm">NIFTY 50 breadth {data.nifty50_breadth.advances}/{data.nifty50_breadth.declines}.</p>
          </section>
          <section className="grid gap-3 md:grid-cols-2">
            {data.indices.map((row) => (
              <article key={row.id} className="panel p-4">
                <div className="flex items-start justify-between gap-3">
                  <h2>{row.name}</h2>
                  <Link href={`/options?index=${encodeURIComponent(row.id)}`} className="pill">OPTION CHAIN</Link>
                </div>
                {row.move.available ? (
                  <p className={`mt-2 text-xl ${((row.move.change_pct ?? 0) >= 0) ? "move-up" : "move-down"}`}>{pct(row.move.change_pct)}</p>
                ) : (
                  <p className="text-down">{row.move.reason || row.intraday_error || "Window unavailable"}</p>
                )}
                <p className="text-xs text-mute">{row.move.from} → {row.move.to} · {row.move.confirmation} · bars {row.intraday_count}</p>
                <p className="text-xs text-mute">{row.move.triggered ? "Threshold breached." : "Threshold not breached."}</p>
                <p className="text-xs">{row.gap.available ? `Opening gap ${pct(row.gap.gap_pct)}` : row.gap.reason}</p>
                <p className="text-xs text-mute">{row.vwap ? `VWAP ${row.vwap.value ?? "unavailable"} · last ${row.vwap.above == null ? "—" : row.vwap.above ? "above" : "below"}` : "No intraday VWAP."}</p>
              </article>
            ))}
          </section>
          <ul className="text-sm text-mute">{data.limitations.map((line) => <li key={line}>{line}</li>)}</ul>
        </>
      )}
    </div>
  );
}
