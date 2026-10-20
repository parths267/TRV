"use client";

import { useEffect, useState } from "react";
import { AutoTrader } from "@/components/AutoTrader";
import { PageHead } from "@/components/PageHead";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";
import { num } from "@/lib/format";

type Position = {
  symbol: string;
  quantity: number;
  avg_price: number;
  last_price: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
};

export default function PaperPage() {
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ positions: Position[] }>("/api/v1/paper")
      .then((body) => setPositions(body.positions))
      .catch((err: Error) => setError(err.message));
  }, []);

  const open = (positions || []).filter((row) => row.quantity !== 0);
  const closed = (positions || []).filter((row) => row.quantity === 0);

  return (
    <div className="grid gap-4">
      <PageHead
        kicker="Trading"
        title="Paper trading"
        lede="Open positions are still on the book. Closed positions are the ones that have been squared off."
      />
      {error && <Failure error={error} />}
      <section className="panel overflow-x-auto p-4 md:p-5">
        <h2>Open positions</h2>
        {positions === null && !error ? <p className="text-sm text-mute">Loading positions…</p> : positions && open.length === 0 ? <p className="text-sm text-mute">No open paper positions.</p> : (
          <table className="range-table">
            <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>Last</th><th>Open P&L</th></tr></thead>
            <tbody>
              {open.map((row) => (
                <tr key={row.symbol}>
                  <td className="font-semibold">{row.symbol}</td>
                  <td className="num">{row.quantity}</td>
                  <td className="num">{inr(row.avg_price)}</td>
                  <td className="num">{row.last_price == null ? "—" : inr(row.last_price)}</td>
                  <td className={`num ${pnlClass(row.unrealized_pnl)}`}>{signed(row.unrealized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="panel overflow-x-auto p-4 md:p-5">
        <h2>Closed positions</h2>
        {positions === null && !error ? <p className="text-sm text-mute">Loading positions…</p> : positions && closed.length === 0 ? <p className="text-sm text-mute">No closed paper positions yet.</p> : (
          <table className="range-table">
            <thead><tr><th>Symbol</th><th>Realized P&L</th></tr></thead>
            <tbody>
              {closed.map((row) => (
                <tr key={row.symbol}>
                  <td className="font-semibold">{row.symbol}</td>
                  <td className={`num ${pnlClass(row.realized_pnl)}`}>{signed(row.realized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <AutoTrader />
    </div>
  );
}

function inr(value: number) {
  return `₹${num(value)}`;
}

function signed(value: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}₹${num(value)}`;
}

function pnlClass(value: number | null) {
  if (value == null || value === 0) return "";
  return value > 0 ? "text-up" : "text-down";
}
