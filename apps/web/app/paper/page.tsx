"use client";

import { useEffect, useState } from "react";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";
import { num } from "@/lib/format";

type State = {
  cash: number;
  positions: { symbol: string; quantity: number; avg_price: number; last_price: number | null; unrealized_pnl: number | null; realized_pnl: number }[];
  orders: { id: string; symbol: string; side: string; quantity: number; fill_price: number; fees: number; note: string; data_as_of?: string }[];
  live_trading_enabled: boolean;
};

export default function PaperPage() {
  const [state, setState] = useState<State | null>(null);
  const [symbol, setSymbol] = useState("RELIANCE");
  const [quantity, setQuantity] = useState(1);
  const [error, setError] = useState("");

  async function load() {
    try {
      setState(await api("/api/v1/paper"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Paper account failed");
    }
  }
  useEffect(() => { load(); }, []);

  async function order(side: "buy" | "sell") {
    setError("");
    try {
      await api("/api/v1/paper/orders", { method: "POST", body: JSON.stringify({ symbol, side, quantity }) });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Order rejected");
    }
  }

  return (
    <div className="grid gap-4">
      <section className="panel p-4">
        <h1 className="text-xl font-semibold">Paper trading</h1>
        <p className="text-sm text-mute">Fills use the latest delayed quote, slippage, and an approximate delivery fee. This is not a broker order. Live trading is {state?.live_trading_enabled ? "on" : "off"}.</p>
        <p className="mt-2 font-mono text-2xl">Cash {state ? num(state.cash) : "—"} INR</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
          <input type="number" min={1} value={quantity} onChange={(event) => setQuantity(Number(event.target.value))} />
          <button type="button" onClick={() => order("buy")}>Buy</button>
          <button className="ghost" type="button" onClick={() => order("sell")}>Sell</button>
        </div>
      </section>
      {error && <Failure error={error} />}
      <section className="panel p-4">
        <h2>Positions</h2>
        {(state?.positions.length || 0) === 0 ? <p className="text-sm text-mute">No paper positions.</p> : (
          <table>
            <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>Last</th><th>Open P&L</th><th>Realized</th></tr></thead>
            <tbody>
              {state?.positions.map((row) => (
                <tr key={row.symbol}>
                  <td>{row.symbol}</td>
                  <td>{row.quantity}</td>
                  <td className="font-mono">{num(row.avg_price)}</td>
                  <td className="font-mono">{num(row.last_price)}</td>
                  <td className="font-mono">{num(row.unrealized_pnl)}</td>
                  <td className="font-mono">{num(row.realized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="panel p-4">
        <h2>Fills</h2>
        {(state?.orders.length || 0) === 0 ? <p className="text-sm text-mute">No fills yet.</p> : (
          <table>
            <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Fill</th><th>Fees</th><th>Note</th></tr></thead>
            <tbody>
              {state?.orders.map((row) => (
                <tr key={row.id}><td>{row.symbol}</td><td>{row.side}</td><td>{row.quantity}</td><td className="font-mono">{num(row.fill_price)}</td><td>{num(row.fees)}</td><td className="text-xs">{row.note} · {row.data_as_of}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
