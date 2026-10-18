"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Empty, Failure, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { listedLogoUrl } from "@/lib/logos";
import { num } from "@/lib/format";

type Stock = {
  symbol: string;
  company: string;
  sector: string;
  price: number;
  bar_time?: string;
  metrics: { label: string; value: string }[];
  chart: string;
};

type Screen = {
  id: string;
  title: string;
  summary: string;
  rule: string;
  status: string;
  reason?: string;
  universe?: string;
  scanned?: number;
  skipped?: number;
  matched?: number;
  stocks: Stock[];
  sectors?: { sector: string; excess_20_pct: number; count: number; rank: number }[];
  limitations?: string[];
  benchmark?: string;
};

export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [data, setData] = useState<Screen | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    api<Screen>(`/api/v1/strategies/screens/${encodeURIComponent(id)}`)
      .then(setData)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div className="grid gap-4">
      <Link href="/strategies" className="text-sm font-semibold text-[var(--primary)]">Back to strategies</Link>
      {loading && <Loading label="Checking large, mid, and small-cap index names on daily bars" />}
      {error && <Failure error={error} />}
      {data && (
        <>
          <section>
            <h1 className="text-2xl font-semibold">{data.title}</h1>
            <p className="mt-1 text-sm text-mute">{data.summary}</p>
            <p className="mt-2 max-w-3xl text-sm">{data.rule}</p>
          </section>
          {data.status !== "ready" ? (
            <Empty title="This screen has no stock list yet" body={data.reason || "The data this rule needs is not connected."} />
          ) : (
            <>
              <p className="text-sm text-mute">
                {data.matched ?? 0} of {data.scanned ?? 0} names matched.
                {data.skipped ? ` ${data.skipped} had too little history.` : ""}
                {data.benchmark ? ` Compared with ${data.benchmark} where the rule uses a benchmark.` : ""}
              </p>
              {!!data.sectors?.length && (
                <div className="flex flex-wrap gap-2">
                  {data.sectors.slice(0, 6).map((sector) => (
                    <span key={sector.sector} className="rounded-full bg-white px-3 py-1 text-sm">
                      {sector.rank}. {sector.sector} {sector.excess_20_pct > 0 ? "+" : ""}{sector.excess_20_pct.toFixed(2)}%
                    </span>
                  ))}
                </div>
              )}
              {data.stocks.length === 0 ? (
                <Empty title="No names matched" body="None of the index names with enough daily history passed this rule on the latest bar." />
              ) : (
                <StockTable stocks={data.stocks} />
              )}
            </>
          )}
          {!!data.limitations?.length && (
            <ul className="grid gap-1 text-xs text-mute">
              {data.limitations.map((line) => <li key={line}>{line}</li>)}
            </ul>
          )}
          {data.universe && <p className="text-xs text-mute">{data.universe}</p>}
        </>
      )}
    </div>
  );
}

function StockTable({ stocks }: { stocks: Stock[] }) {
  const columns = stocks[0]?.metrics.map((metric) => metric.label) ?? [];
  return (
    <div className="panel overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Company</th>
            <th>Symbol</th>
            <th>Sector</th>
            <th>Price</th>
            {columns.map((label) => <th key={label}>{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock) => (
            <tr key={stock.symbol}>
              <td>
                <Link href={stock.chart} className="flex items-center gap-3 font-semibold">
                  <Mark symbol={stock.symbol} label={stock.company} />
                  {stock.company}
                </Link>
              </td>
              <td className="font-semibold">{stock.symbol}</td>
              <td className="text-mute">{stock.sector}</td>
              <td className="font-semibold">₹{num(stock.price)}</td>
              {columns.map((label) => {
                const value = stock.metrics.find((metric) => metric.label === label)?.value ?? "—";
                return <td key={label} className={`font-semibold ${metricTone(value)}`}>{value}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function metricTone(value: string) {
  if (value.startsWith("+")) return "text-up";
  if (value.startsWith("-") && /\d/.test(value)) return "text-down";
  return "";
}

function Mark({ symbol, label }: { symbol: string; label: string }) {
  const [failed, setFailed] = useState(false);
  const letter = label.replace(/[^A-Za-z0-9]/g, "").slice(0, 1).toUpperCase() || "?";
  return (
    <span className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-lg border border-[var(--line)] bg-white text-xs font-bold text-[var(--primary)]">
      {failed ? letter : <img src={listedLogoUrl(symbol)} alt="" className="h-6 w-6 object-contain" onError={() => setFailed(true)} />}
    </span>
  );
}
