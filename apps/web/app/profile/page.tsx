"use client";

import { useEffect, useState } from "react";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";
import { num } from "@/lib/format";

type Me = {
  email: string;
  name: string;
  plan: string;
  theme: string;
  quiet_start?: string | null;
  quiet_end?: string | null;
  telegram_chat_id?: string | null;
  email_verified: boolean;
};

type Position = {
  symbol: string;
  quantity: number;
  avg_price: number;
  last_price: number | null;
  realized_pnl: number;
};

type Order = {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  fill_price: number;
  fees: number;
  note: string;
  created_at?: string;
};

export default function ProfilePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [cash, setCash] = useState<number | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState(false);

  useEffect(() => {
    api<Me>("/api/v1/auth/me").then(setMe).catch((err: Error) => setError(err.message));
    api<{ cash: number; positions: Position[]; orders: Order[] }>("/api/v1/paper")
      .then((body) => {
        setCash(body.cash);
        setPositions(body.positions);
        setOrders(body.orders);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const open = positions.filter((row) => row.quantity !== 0);
  const invested = open.reduce((sum, row) => sum + (row.last_price == null ? 0 : row.last_price * row.quantity), 0);
  const marked = open.filter((row) => row.last_price != null).length;
  const total = cash == null ? null : cash + invested;
  const closed = positions.filter((row) => row.quantity === 0);
  const initial = (me?.name || me?.email || "?").replace(/[^A-Za-z0-9]/g, "").slice(0, 1).toUpperCase() || "?";

  function applyTheme(theme: string) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("bazaar_theme", theme);
  }

  return (
    <div className="mx-auto grid max-w-xl gap-4">
      {error && <Failure error={error} />}
      <section className="panel p-4">
        <div className="flex items-center gap-3 border-b border-[var(--line)] pb-4">
          <span className="grid h-12 w-12 place-items-center rounded-full bg-[var(--surface)] text-lg font-semibold">{initial}</span>
          <div className="min-w-0">
            <div className="font-semibold">{me?.name || "Account"}</div>
            <div className="truncate text-sm text-mute">{me?.email || "Loading profile…"}</div>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 py-4">
          <div className="flex items-center gap-3">
            <span className="account-icon">₹</span>
            <div>
              <div className="text-lg font-semibold">{total == null ? "—" : `₹${num(total)}`}</div>
              <div className="text-sm text-mute">Total paper value</div>
            </div>
          </div>
          <div className="text-right">
            <div className="font-semibold text-up">{cash == null ? "—" : `₹${num(cash)}`}</div>
            <div className="text-xs text-mute">Remaining cash</div>
          </div>
        </div>
        <p className="text-xs text-mute">
          Remaining cash is what is left to deploy. Total adds the latest mark of {marked} open position{marked === 1 ? "" : "s"}. This is paper money, not a bank balance.
        </p>
      </section>

      <section className="panel px-4">
        <button className="account-row" type="button" onClick={() => setEditing((value) => !value)}>
          <span className="account-icon">Aa</span>
          <span className="min-w-0 flex-1 text-left">
            <span className="block font-semibold">Update profile</span>
            <span className="block text-sm text-mute">Name, theme, quiet hours, Telegram</span>
          </span>
          <span className="text-mute">{editing ? "–" : ">"}</span>
        </button>
        {editing && me && (
          <form className="grid gap-3 border-b border-[var(--line)] pb-4" onSubmit={async (event) => {
            event.preventDefault();
            const saved = await api<Me>("/api/v1/auth/me", { method: "PATCH", body: JSON.stringify(me) });
            setMe(saved);
            applyTheme(saved.theme);
            setMessage("Profile saved.");
          }}>
            <label className="grid gap-1 text-sm">Name
              <input value={me.name} onChange={(event) => setMe({ ...me, name: event.target.value })} />
            </label>
            <label className="grid gap-1 text-sm">Theme
              <select value={me.theme} onChange={(event) => setMe({ ...me, theme: event.target.value })}>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm">Quiet hours start
              <input placeholder="22:00" value={me.quiet_start || ""} onChange={(event) => setMe({ ...me, quiet_start: event.target.value })} />
            </label>
            <label className="grid gap-1 text-sm">Quiet hours end
              <input placeholder="08:00" value={me.quiet_end || ""} onChange={(event) => setMe({ ...me, quiet_end: event.target.value })} />
            </label>
            <label className="grid gap-1 text-sm">Telegram chat id
              <input value={me.telegram_chat_id || ""} onChange={(event) => setMe({ ...me, telegram_chat_id: event.target.value })} />
            </label>
            <button type="submit">Save profile</button>
            {message && <p className="text-sm text-mute">{message}</p>}
          </form>
        )}
        <button className="account-row" type="button" onClick={() => setHistory((value) => !value)}>
          <span className="account-icon">☰</span>
          <span className="min-w-0 flex-1 text-left">
            <span className="block font-semibold">Position history</span>
            <span className="block text-sm text-mute">{closed.length} closed · {orders.length} fills</span>
          </span>
          <span className="text-mute">{history ? "–" : ">"}</span>
        </button>
      </section>

      {history && (
        <section className="panel overflow-x-auto p-4">
          <h2>Closed positions</h2>
          {closed.length === 0 ? <p className="text-sm text-mute">No closed positions yet.</p> : (
            <table className="range-table">
              <thead><tr><th>Symbol</th><th>Realized P&L</th></tr></thead>
              <tbody>
                {closed.map((row) => (
                  <tr key={row.symbol}>
                    <td className="font-semibold">{row.symbol}</td>
                    <td className={`num ${row.realized_pnl > 0 ? "text-up" : row.realized_pnl < 0 ? "text-down" : ""}`}>{signed(row.realized_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h2 className="mt-5">Fills</h2>
          {orders.length === 0 ? <p className="text-sm text-mute">No fills yet.</p> : (
            <table className="range-table">
              <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Fill</th><th>Fees</th></tr></thead>
              <tbody>
                {orders.map((row) => (
                  <tr key={row.id}>
                    <td className="font-semibold">{row.symbol}</td>
                    <td className="num">{row.side}</td>
                    <td className="num">{row.quantity}</td>
                    <td className="num">₹{num(row.fill_price)}</td>
                    <td className="num">₹{num(row.fees)}</td>
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

function signed(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}₹${num(value)}`;
}
