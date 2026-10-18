"use client";

import { useEffect, useState } from "react";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";
import { num, pct, tone } from "@/lib/format";

type List = { id: string; name: string; items: { symbol: string; exchange: string }[] };
type Book = {
  holdings: { symbol: string; quantity: number; avg_price: number; last_price: number | null; unrealized_pnl: number | null; sector: string; quote_error?: string }[];
  invested: number;
  market_value: number;
  unrealized_pnl: number | null;
  sector_weights: { sector: string; weight_pct: number }[];
  realized_note: string;
};

export default function PortfolioPage() {
  const [lists, setLists] = useState<List[]>([]);
  const [name, setName] = useState("Core");
  const [symbol, setSymbol] = useState("INFY");
  const [book, setBook] = useState<Book | null>(null);
  const [error, setError] = useState("");
  const [holding, setHolding] = useState({ symbol: "TCS", quantity: 10, avg_price: 0 });

  async function load() {
    try {
      const [watchlists, portfolio] = await Promise.all([
        api<{ watchlists: List[] }>("/api/v1/watchlists"),
        api<Book>("/api/v1/portfolio"),
      ]);
      setLists(watchlists.watchlists);
      setBook(portfolio);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portfolio failed");
    }
  }
  useEffect(() => { load(); }, []);

  return (
    <div className="grid gap-4">
      <section className="panel p-4">
        <h1 className="text-xl font-semibold">Watchlists</h1>
        <div className="mt-3 flex flex-wrap gap-2">
          <input value={name} onChange={(event) => setName(event.target.value)} />
          <button type="button" onClick={async () => {
            await api("/api/v1/watchlists", { method: "POST", body: JSON.stringify({ name }) });
            load();
          }}>Create</button>
        </div>
        {lists.length === 0 && <p className="mt-3 text-sm text-mute">No watchlists yet.</p>}
        {lists.map((list) => (
          <div key={list.id} className="mt-4">
            <div className="font-medium">{list.name}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
              <button type="button" onClick={async () => {
                await api(`/api/v1/watchlists/${list.id}/symbols`, { method: "POST", body: JSON.stringify({ symbol, exchange: "NSE" }) });
                load();
              }}>Add</button>
            </div>
            <ul className="mt-2 text-sm">{list.items.map((item) => <li key={item.symbol}>{item.exchange}:{item.symbol}</li>)}</ul>
          </div>
        ))}
      </section>
      <section className="panel p-4">
        <h2>Holdings</h2>
        <p className="text-sm text-mute">{book?.realized_note}</p>
        <p className="mt-2 text-sm">Invested {num(book?.invested)} · value {num(book?.market_value)} · open P&L <span className={tone(book?.unrealized_pnl)}>{num(book?.unrealized_pnl)}</span></p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input value={holding.symbol} onChange={(event) => setHolding({ ...holding, symbol: event.target.value.toUpperCase() })} />
          <input type="number" value={holding.quantity} onChange={(event) => setHolding({ ...holding, quantity: Number(event.target.value) })} />
          <input type="number" placeholder="Average price" value={holding.avg_price || ""} onChange={(event) => setHolding({ ...holding, avg_price: Number(event.target.value) })} />
          <button type="button" onClick={async () => {
            await api("/api/v1/portfolio/holdings", { method: "POST", body: JSON.stringify(holding) });
            load();
          }}>Save holding</button>
        </div>
        <table className="mt-3">
          <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>Last</th><th>P&L</th><th>Sector</th></tr></thead>
          <tbody>
            {book?.holdings.map((row) => (
              <tr key={row.symbol}>
                <td>{row.symbol}</td>
                <td>{row.quantity}</td>
                <td className="font-mono">{num(row.avg_price)}</td>
                <td className="font-mono">{row.quote_error || num(row.last_price)}</td>
                <td className="font-mono">{num(row.unrealized_pnl)}</td>
                <td>{row.sector}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          {book?.sector_weights.map((row) => <span key={row.sector} className="panel px-2 py-1">{row.sector} {pct(row.weight_pct)}</span>)}
        </div>
      </section>
      {error && <Failure error={error} onRetry={load} />}
    </div>
  );
}
