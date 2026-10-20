"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { Failure, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { listedLogoUrl } from "@/lib/logos";

type Row = {
  symbol: string;
  company?: string;
  close?: number;
  reference_high?: number;
  reference_low?: number;
  distance_from_high_pct?: number;
  distance_from_low_pct?: number;
  relative_volume?: number | null;
  sessions_used?: number;
  partial_history?: boolean;
  bar_time?: string;
  chart: string;
  volume_confirmed?: boolean;
  status: string;
  tone: "up" | "down";
};

type Payload = {
  method?: string;
  new_closing_highs?: Omit<Row, "status" | "tone">[];
  new_intraday_highs?: Omit<Row, "status" | "tone">[];
  approaching_highs?: Omit<Row, "status" | "tone">[];
  new_closing_lows?: Omit<Row, "status" | "tone">[];
  new_intraday_lows?: Omit<Row, "status" | "tone">[];
  approaching_lows?: Omit<Row, "status" | "tone">[];
  unavailable?: { symbol: string; reason?: string }[];
};

const GROUPS = [
  ["new_closing_highs", "New closing high", "up"],
  ["new_intraday_highs", "Intraday high", "up"],
  ["approaching_highs", "Near 52-week high", "up"],
  ["new_closing_lows", "New closing low", "down"],
  ["new_intraday_lows", "Intraday low", "down"],
  ["approaching_lows", "Near 52-week low", "down"],
] as const;

export default function HighsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState<Payload | null>(null);
  const [filter, setFilter] = useState<"all" | "up" | "down">("all");

  function load() {
    setLoading(true);
    setError("");
    api<Payload>("/api/v1/highs?approach_pct=2")
      .then(setData)
      .catch((err: Error) => setError(err.message || "Range study failed"))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  const rows = useMemo(() => flatten(data).filter((row) => filter === "all" || row.tone === filter), [data, filter]);
  const all = useMemo(() => flatten(data), [data]);
  const highs = all.filter((row) => row.tone === "up").length;
  const lows = all.filter((row) => row.tone === "down").length;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageHead
          kicker="Market"
          title="52-week range"
          lede="NIFTY 50 names at a new high or low, or within 2% of one. The range uses up to 252 prior daily sessions and leaves out the latest bar."
        />
        <button className="ghost" type="button" onClick={load} disabled={loading}>{loading ? "Calculating" : "Refresh"}</button>
      </div>
      {loading && !data && <Loading label="Calculating the 52-week range" />}
      {error && <Failure error={error} onRetry={load} />}
      {data && (
        <section className="panel overflow-x-auto p-4 md:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="chip-row">
              <button type="button" data-on={filter === "all"} onClick={() => setFilter("all")}>All {all.length}</button>
              <button type="button" data-on={filter === "up"} onClick={() => setFilter("up")}>Highs {highs}</button>
              <button type="button" data-on={filter === "down"} onClick={() => setFilter("down")}>Lows {lows}</button>
            </div>
            <p className="text-xs text-mute">{data.unavailable?.length ? `${data.unavailable.length} names had too little history.` : "Prior 252 sessions, latest bar excluded."}</p>
          </div>
          {rows.length === 0 ? (
            <p className="text-sm text-mute">None of the latest bars are within 2% of the 52-week high or low.</p>
          ) : (
            <table className="range-table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Close</th>
                  <th>52w high</th>
                  <th>52w low</th>
                  <th>Below high</th>
                  <th>Above low</th>
                  <th>In the range</th>
                  <th>Rel vol</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.status}-${row.symbol}`}>
                    <td>
                      <Link href={row.chart} className="range-name">
                        <Logo symbol={row.symbol} label={row.company || row.symbol} />
                        <span>
                          <span className="block font-semibold">{row.symbol}</span>
                          <span className="block text-xs font-normal text-mute">{row.company}</span>
                        </span>
                      </Link>
                    </td>
                    <td className="num font-semibold">{inr(row.close)}</td>
                    <td className="num">{inr(row.reference_high)}</td>
                    <td className="num">{inr(row.reference_low)}</td>
                    <td className={`num ${row.tone === "up" ? "text-up" : ""}`}>{distance(row.distance_from_high_pct, "above")}</td>
                    <td className={`num ${row.tone === "down" ? "text-down" : ""}`}>{distance(row.distance_from_low_pct, "below")}</td>
                    <td className="num"><Meter high={row.distance_from_high_pct} low={row.distance_from_low_pct} /></td>
                    <td className="num">{row.relative_volume == null ? "—" : `${row.relative_volume.toFixed(2)}x`}</td>
                    <td className="num">
                      <span className={row.tone === "up" ? "move-up" : "move-down"}>{row.status}</span>
                      {row.partial_history && <div className="mt-1 text-xs font-normal text-mute">{row.sessions_used} sessions</div>}
                    </td>
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

function flatten(data: Payload | null): Row[] {
  if (!data) return [];
  const rows: Row[] = [];
  for (const [key, status, tone] of GROUPS) {
    for (const row of data[key] || []) {
      rows.push({ ...row, status, tone });
    }
  }
  return rows.sort((a, b) => (a.distance_from_high_pct ?? 0) - (b.distance_from_high_pct ?? 0));
}

function Logo({ symbol, label }: { symbol: string; label: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="mark">{label.replace(/[^A-Za-z0-9]/g, "").slice(0, 1) || "?"}</span>;
  return <img src={listedLogoUrl(symbol)} alt="" onError={() => setFailed(true)} />;
}

function Meter({ high, low }: { high?: number; low?: number }) {
  const spot = position(high, low);
  if (spot == null) return <>—</>;
  return (
    <div className="range-meter" title={`${spot.toFixed(0)}% of the way from the low to the high`}>
      <i style={{ left: `${spot}%` }} />
    </div>
  );
}

function position(high?: number, low?: number) {
  if (high == null || low == null || Number.isNaN(high) || Number.isNaN(low)) return null;
  if (high < 0) return 100;
  if (low < 0) return 0;
  const span = high + low;
  if (span <= 0) return 50;
  return Math.min(100, Math.max(0, (low / span) * 100));
}

function distance(value: number | undefined, beyond: "above" | "below") {
  if (value == null || Number.isNaN(value)) return "—";
  if (value < 0) return `${Math.abs(value).toFixed(2)}% ${beyond}`;
  return `${value.toFixed(2)}%`;
}

function inr(value?: number) {
  if (value == null || Number.isNaN(value)) return "—";
  return `₹${num(value)}`;
}
