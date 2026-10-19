"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { num, tone } from "@/lib/format";

type Trade = {
  date: string; instrument: string; expiry: string; mode: string; side: string;
  t_in: string; t_out: string; reason: string; legs: string; net: string; fees: string; why: string;
};

type Overview = {
  status: {
    state: string; message: string; heartbeat?: string; symbol?: string; expiry?: string; spot?: number;
    trades_today?: number; day_pnl?: number;
    position?: { side: string; mode: string; legs: { strike: number; typ: string; qty: number; entry: number; mark: number }[]; tp: number; sl: number; mult: number } | null;
    last_decision?: { side: string; score: number; why: string } | null;
    upstox?: { current: boolean; saved_at: string | null; source: string | null; auto_login: boolean; auto_login_error: string | null };
  };
  stopped: boolean;
  summary: { trades: number; win_pct?: number; expectancy?: number; profit_factor?: number | null; net_pnl?: number; breakeven_win_pct?: number | null };
  trades: Trade[];
  decisions: { at: string; symbol: string; side: string; score: number; why: string }[];
  rules: Record<string, string | number | string[]>;
  telegram: boolean;
};

const STATE_LABEL: Record<string, string> = {
  running: "Running",
  idle: "Waiting for the market",
  login_needed: "Upstox login needed",
  no_expiry: "No expiry today",
  error: "Error",
  not_started: "Not started",
};

export function AutoTrader() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    api<Overview>("/api/v1/autotrader").then((body) => { setData(body); setError(""); }).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 20000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function testTelegram() {
    try {
      await api("/api/v1/autotrader/telegram-test", { method: "POST" });
      setNote("Test message sent to Telegram.");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Telegram test failed");
    }
  }

  async function toggle() {
    try {
      await api(data?.stopped ? "/api/v1/autotrader/resume" : "/api/v1/autotrader/stop", { method: "POST" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  }

  if (error && !data) return <section className="panel p-4 text-sm text-mute">Auto trader: {error}</section>;
  if (!data) return null;
  const status = data.status;
  const position = status.position;
  const live = status.state === "running";
  const sum = data.summary;

  return (
    <section className="panel grid gap-4 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">Auto trader</h2>
            <span className="pill" style={live ? undefined : { background: "var(--surface)", color: "var(--mute)" }}>
              {data.stopped ? "STOPPED" : (STATE_LABEL[status.state] || status.state).toUpperCase()}
            </span>
          </div>
          <p className="mt-1 text-sm text-mute">{status.message}</p>
          {status.upstox && <TokenLine info={status.upstox} />}
          <p className="text-xs text-mute">
            {data.rules.mode === "spread" ? "Credit spreads" : "Long options"} on {(data.rules.underlyings as string[]).join(" and ")} within {data.rules.max_dte} day of expiry.
            Entries {data.rules.entry_window}, square-off {data.rules.squareoff}. Score at least {data.rules.min_score} of 5 plus a breakout.
            {" "}Up to {data.rules.max_trades} trades a day, ₹{num(Number(data.rules.daily_loss_cap), 0)} daily loss cap, no entries above India VIX {data.rules.vix_max}.
          </p>
        </div>
        <div className="grid justify-items-end gap-2">
          <div className="flex gap-2">
            <button className="ghost" type="button" onClick={testTelegram}>Test Telegram</button>
            <button className={data.stopped ? "" : "ghost"} type="button" onClick={toggle}>
              {data.stopped ? "Resume" : "Stop and flatten"}
            </button>
          </div>
          <span className="text-xs text-mute">
            {note || (data.telegram ? "Telegram alerts are on." : "Telegram alerts are off: add the bot token and your chat id.")}
          </span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Instrument" value={status.symbol ? `${status.symbol} · ${status.expiry}` : "—"} />
        <Stat label="Today" value={`${status.trades_today ?? 0} trades`} sub={status.day_pnl == null ? undefined : `₹${num(status.day_pnl)}`} subTone={tone(status.day_pnl)} />
        <Stat label="All paper trades" value={`${sum.trades}`} sub={sum.trades ? `Win ${sum.win_pct}% · breakeven ${sum.breakeven_win_pct ?? "—"}%` : undefined} />
        <Stat label="Expectancy per trade" value={sum.expectancy == null ? "—" : `₹${num(sum.expectancy)}`} sub={sum.profit_factor == null ? undefined : `Profit factor ${sum.profit_factor}`} subTone={tone(sum.expectancy)} />
      </div>

      {position && (
        <div className="rounded-xl border border-[var(--line)] p-3 text-sm">
          <div className="font-semibold">Open {position.side === "CALL" ? "bullish" : "bearish"} {position.mode}</div>
          <div className="mt-1 font-mono text-xs">
            {position.legs.map((leg) => `${leg.qty > 0 ? "+" : "−"}${leg.strike}${leg.typ} @ ${num(leg.entry)} now ${num(leg.mark)}`).join("  |  ")}
          </div>
          <div className="mt-1 text-xs text-mute">Target ₹{num(position.tp * position.mult)} · stop ₹{num(position.sl * position.mult)}</div>
        </div>
      )}

      {status.last_decision && (
        <p className="text-xs text-mute">
          Last bar: <span className="font-semibold text-[var(--text)]">{status.last_decision.side}</span> score {status.last_decision.score}. {status.last_decision.why}
        </p>
      )}

      <div className="overflow-x-auto">
        <h3 className="mb-2 text-sm font-semibold">Paper fills</h3>
        {data.trades.length === 0 ? <p className="text-sm text-mute">No automatic trades yet.</p> : (
          <table>
            <thead><tr><th>Date</th><th>Index</th><th>Side</th><th>In</th><th>Out</th><th>Exit</th><th>Legs</th><th>Fees</th><th>Net</th></tr></thead>
            <tbody>
              {data.trades.map((row, index) => (
                <tr key={`${row.date}-${row.t_in}-${index}`}>
                  <td>{row.date}</td><td>{row.instrument}</td><td>{row.side}</td><td>{row.t_in}</td><td>{row.t_out}</td>
                  <td>{row.reason}</td><td className="font-mono text-xs">{row.legs}</td>
                  <td>{row.fees ? num(Number(row.fees)) : "—"}</td>
                  <td className={`font-semibold ${tone(row.net ? Number(row.net) : null)}`}>{row.net ? num(Number(row.net)) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data.decisions.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold">Recent bar decisions</summary>
          <ul className="mt-2 grid gap-1 text-xs text-mute">
            {data.decisions.map((row) => (
              <li key={row.at}>{row.at.slice(11, 16)} {row.symbol} <span className="font-semibold text-[var(--text)]">{row.side}</span> {row.score}: {row.why}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function TokenLine({ info }: { info: NonNullable<Overview["status"]["upstox"]> }) {
  const saved = info.saved_at
    ? new Date(info.saved_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : null;
  const tokenText = info.current
    ? `Upstox token valid until 03:30 IST, issued ${saved}${info.source === "totp" ? " by automatic login" : ""}.`
    : "Upstox token expired.";
  const autoText = info.auto_login
    ? info.auto_login_error ? ` Automatic login failed: ${info.auto_login_error}.` : " Automatic login runs from 08:45 IST on weekdays."
    : " Automatic login is off: add UPSTOX_PIN and UPSTOX_TOTP_SECRET to .env.";
  return <p className={`text-xs ${info.current ? "text-mute" : "text-[var(--down)]"}`}>{tokenText}{autoText}</p>;
}

function Stat({ label, value, sub, subTone }: { label: string; value: string; sub?: string; subTone?: string }) {
  return (
    <div className="rounded-xl border border-[var(--line)] p-3">
      <div className="text-xs text-mute">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
      {sub && <div className={`text-xs ${subTone || "text-mute"}`}>{sub}</div>}
    </div>
  );
}
