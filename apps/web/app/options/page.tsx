"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Failure, Loading } from "@/components/States";
import { API_URL, api, type ApiError } from "@/lib/api";
import { num, tone } from "@/lib/format";

type Leg = {
  trading_symbol: string | null;
  ltp: number | null;
  close: number | null;
  oi: number | null;
  prev_oi: number | null;
  iv: number | null;
  delta: number | null;
  theta: number | null;
  gamma: number | null;
};

type Chain = {
  index: string;
  name: string;
  available: boolean;
  reason: string | null;
  spot: number | null;
  expiry: string | null;
  expiries: string[];
  lot_size: number | null;
  max_lots: number | null;
  max_lots_note?: string | null;
  rows: { strike: number; call: Leg | null; put: Leg | null }[];
  indexes: { id: string; name: string }[];
  session: { label: string; state?: string };
};

type Paper = {
  cash: number;
  positions: { symbol: string; quantity: number; avg_price: number; unrealized_pnl: number | null }[];
};

type Quote = { display_symbol?: string; price?: number; change_pct?: number | null };
type Pick = { right: "CE" | "PE"; strike: number };

const PREFIX: Record<string, RegExp> = {
  nifty50: /^NIFTY /,
  banknifty: /^BANKNIFTY /,
  niftyfin: /^FINNIFTY /,
  sensex: /^SENSEX /,
};

export default function OptionsPage() {
  return (
    <Suspense fallback={<Loading label="Loading the option chain" />}>
      <ChainBoard />
    </Suspense>
  );
}

function ChainBoard() {
  const router = useRouter();
  const params = useSearchParams();
  const index = params.get("index") || "nifty50";
  const expiry = params.get("expiry") || "";
  const [chain, setChain] = useState<Chain | null>(null);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [error, setError] = useState("");
  const [login, setLogin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [pick, setPick] = useState<Pick | null>(null);
  const [lots, setLots] = useState(1);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const scrolled = useRef("");

  const load = useCallback((background = false) => {
    if (!background) {
      setLoading(true);
      setError("");
      setLogin(false);
    }
    const query = new URLSearchParams({ index });
    if (expiry) query.set("expiry", expiry);
    api<Chain>(`/api/v1/market/options?${query}`)
      .then((body) => {
        setChain(body);
        setError("");
      })
      .catch((err: ApiError) => {
        if (!background) {
          setError(err.message || "Option chain failed");
          setLogin(err.status === 401);
        }
      })
      .finally(() => {
        if (!background) setLoading(false);
      });
    api<Paper>("/api/v1/paper").then(setPaper).catch(() => undefined);
    api<{ indices: Quote[] }>("/api/v1/market/pulse")
      .then((body) => {
        const next: Record<string, Quote> = {};
        for (const row of body.indices) {
          if (row.display_symbol) next[row.display_symbol] = row;
        }
        setQuotes(next);
      })
      .catch(() => undefined);
  }, [index, expiry]);

  useEffect(() => {
    if (!chain?.available || loading) return;
    const key = `${chain.index}|${chain.expiry}|${showAll}`;
    if (scrolled.current === key) return;
    const row = document.querySelector(".chain-spot");
    if (!row) return;
    scrolled.current = key;
    row.scrollIntoView({ block: "center" });
  }, [chain, showAll, loading]);

  useEffect(() => {
    setShowAll(false);
    setPick(null);
    load(false);
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") load(true);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!pick) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setPick(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pick]);

  function openStrike(strike: number, right?: "CE" | "PE") {
    const row = chain?.rows.find((item) => item.strike === strike);
    const callOk = Boolean(row?.call?.trading_symbol && (row.call.ltp ?? 0) > 0);
    const putOk = Boolean(row?.put?.trading_symbol && (row.put.ltp ?? 0) > 0);
    if (!callOk && !putOk) return;
    const next = right === "PE" ? (putOk ? "PE" : "CE") : right === "CE" ? (callOk ? "CE" : "PE") : (callOk ? "CE" : "PE");
    setLots(1);
    setNotice("");
    setPick({ strike, right: next });
  }

  async function order(side: "buy" | "sell") {
    if (!chain?.expiry || !pick) return;
    setBusy(true);
    setNotice("");
    try {
      const fill = await api<{ fill_price: number; fees: number; cash: number; lots: number; symbol: string }>(
        "/api/v1/paper/option-orders",
        {
          method: "POST",
          body: JSON.stringify({
            index: chain.index,
            expiry: chain.expiry,
            strike: pick.strike,
            right: pick.right,
            side,
            lots,
          }),
        },
      );
      setNotice(`${side === "buy" ? "Bought" : "Sold"} ${fill.lots} lot of ${fill.symbol} at ₹${num(fill.fill_price)}. Fees ₹${num(fill.fees)}. Cash ₹${num(fill.cash)}.`);
      const next = await api<Paper>("/api/v1/paper");
      setPaper(next);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Paper order rejected");
    } finally {
      setBusy(false);
    }
  }

  const indexes = chain?.indexes || [];
  const strikeRow = chain?.rows.find((row) => row.strike === pick?.strike);
  const leg = pick ? (pick.right === "CE" ? strikeRow?.call : strikeRow?.put) : null;
  const held = paper?.positions.find((row) => row.symbol === leg?.trading_symbol);
  const lotSize = chain?.lot_size || 0;
  const maxLots = chain?.max_lots || 1;
  const canSell = Boolean(held && lotSize && held.quantity + 1e-9 >= lotSize * lots);
  const visible = visibleRows(chain, showAll);
  const book = (paper?.positions || []).filter((row) => PREFIX[index]?.test(row.symbol));

  return (
    <div className="grid min-w-0 gap-4">
      <div className="grid items-start gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <Link href="/" className="text-sm text-mute">Market overview</Link>
          <h1 className="mt-1 text-2xl font-semibold">{chain?.name || "Option chain"}</h1>
          <p className="mt-1 text-sm text-mute">
            Premiums come from Upstox. Click a strike to buy a paper contract. Live orders stay off.
            {chain ? ` ${chain.session.label}.` : ""}
          </p>
        </div>
        <div className="text-sm text-mute md:text-right">
          <div>Spot</div>
          <div className="text-2xl font-semibold text-[var(--text)]">{chain?.spot == null ? "—" : `₹${num(chain.spot)}`}</div>
          {quotes[index]?.change_pct != null && (
            <div className={tone(quotes[index].change_pct)}>{signed(quotes[index].change_pct)}</div>
          )}
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {indexes.map((item) => {
          const quote = quotes[item.id];
          const active = item.id === index;
          return (
            <Link
              key={item.id}
              href={`/options?index=${encodeURIComponent(item.id)}`}
              className="panel shrink-0 px-3 py-2"
              style={active ? { borderColor: "var(--primary)" } : undefined}
            >
              <span className="block text-sm font-semibold">{item.name}</span>
              <span className={`block text-xs ${tone(quote?.change_pct)}`}>{quote?.price == null ? "—" : `₹${num(quote.price)}`}</span>
            </Link>
          );
        })}
      </div>

      {loading && <Loading label="Reading the Upstox option chain" />}
      {error && <Failure error={error} onRetry={() => load(false)} />}
      {login && (
        <a className="text-sm font-semibold" style={{ color: "var(--primary)" }} href={`${API_URL}/api/v1/upstox/login`}>
          Sign in to Upstox with mobile OTP
        </a>
      )}

      {chain && !loading && (
        <section className="panel grid gap-3 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1 text-sm">Expiry
              <select
                value={chain.expiry || ""}
                disabled={!chain.expiries.length}
                onChange={(event) => router.push(`/options?index=${encodeURIComponent(index)}&expiry=${event.target.value}`)}
              >
                {chain.expiries.map((item) => <option key={item} value={item}>{expiryLabel(item)}</option>)}
              </select>
            </label>
            <div className="text-sm text-mute">
              Lot size {chain.lot_size ?? "—"}
              {chain.max_lots_note ? ` · ${chain.max_lots_note}` : ""}
            </div>
            <button className="ghost ml-auto w-fit" type="button" onClick={() => load(true)}>Refresh</button>
          </div>

          {!chain.available && <p className="text-sm text-mute">{chain.reason}</p>}
          {chain.available && <p className="text-sm text-mute">Click a strike to buy. Cash ₹{paper ? num(paper.cash) : "—"}.</p>}
        </section>
      )}

      {chain?.available && !loading && (
        <section className="panel chain-scroll p-2">
          <div className="mb-2 flex items-center justify-between px-2">
            <h2 className="text-sm font-semibold">{visible.length} strikes around the spot</h2>
            <button className="ghost w-fit" type="button" onClick={() => setShowAll((value) => !value)}>
              {showAll ? "Show the spot window" : "Show every strike"}
            </button>
          </div>
          <table className="chain-table">
            <thead>
              <tr>
                <th className="chain-call" colSpan={6}>Calls</th>
                <th className="chain-strike">Strike</th>
                <th className="chain-put" colSpan={6}>Puts</th>
              </tr>
              <tr>
                <th className="chain-call">Gamma</th>
                <th className="chain-call">IV</th>
                <th className="chain-call">Theta</th>
                <th className="chain-call">Delta</th>
                <th className="chain-call">OI</th>
                <th className="chain-call">LTP</th>
                <th className="chain-strike" />
                <th className="chain-put">LTP</th>
                <th className="chain-put">OI</th>
                <th className="chain-put">Delta</th>
                <th className="chain-put">Theta</th>
                <th className="chain-put">IV</th>
                <th className="chain-put">Gamma</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => {
                const marker = chain.spot != null && row.strike > chain.spot && !visible.some((item) => item.strike < row.strike && item.strike > (chain.spot as number));
                return (
                  <ChainRows
                    key={row.strike}
                    row={row}
                    spot={marker ? chain.spot : null}
                    pick={pick}
                    onStrike={openStrike}
                  />
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {book.length > 0 && (
        <section className="panel p-4">
          <h2 className="font-semibold">Paper positions on this index</h2>
          <table>
            <thead><tr><th>Contract</th><th>Units</th><th>Avg</th><th>Open P&L</th></tr></thead>
            <tbody>
              {book.map((row) => (
                <tr key={row.symbol}>
                  <td>{row.symbol}</td>
                  <td>{row.quantity}</td>
                  <td className="font-mono">{num(row.avg_price)}</td>
                  <td className={`font-mono ${tone(row.unrealized_pnl)}`}>{num(row.unrealized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {pick && chain?.available && (
        <BuyDialog
          chain={chain}
          pick={pick}
          lots={lots}
          maxLots={maxLots}
          busy={busy}
          notice={notice}
          heldUnits={held?.quantity ?? 0}
          heldAvg={held?.avg_price ?? null}
          canSell={canSell}
          onLots={setLots}
          onRight={(right) => setPick({ strike: pick.strike, right })}
          onClose={() => setPick(null)}
          onOrder={order}
        />
      )}
    </div>
  );
}

function ChainRows({
  row,
  spot,
  pick,
  onStrike,
}: {
  row: { strike: number; call: Leg | null; put: Leg | null };
  spot: number | null;
  pick: Pick | null;
  onStrike: (strike: number, right?: "CE" | "PE") => void;
}) {
  const selected = pick?.strike === row.strike;
  return (
    <>
      {spot != null && (
        <tr className="chain-spot">
          <td colSpan={13}>Spot ₹{num(spot)}</td>
        </tr>
      )}
      <tr>
        <td className="chain-call">{fixed(row.call?.gamma ?? null, 4)}</td>
        <td className="chain-call">{fixed(row.call?.iv ?? null, 2)}</td>
        <td className="chain-call">{fixed(row.call?.theta ?? null, 2)}</td>
        <td className="chain-call">{fixed(row.call?.delta ?? null, 2)}</td>
        <OiCell leg={row.call} klass="chain-call" />
        <PremiumCell leg={row.call} right="CE" strike={row.strike} pick={pick} onStrike={onStrike} klass="chain-call" />
        <td className="chain-strike">
          <button type="button" className="chain-hit ghost" data-on={selected} onClick={() => onStrike(row.strike)}>
            {num(row.strike, 0)}
          </button>
        </td>
        <PremiumCell leg={row.put} right="PE" strike={row.strike} pick={pick} onStrike={onStrike} klass="chain-put" />
        <OiCell leg={row.put} klass="chain-put" />
        <td className="chain-put">{fixed(row.put?.delta ?? null, 2)}</td>
        <td className="chain-put">{fixed(row.put?.theta ?? null, 2)}</td>
        <td className="chain-put">{fixed(row.put?.iv ?? null, 2)}</td>
        <td className="chain-put">{fixed(row.put?.gamma ?? null, 4)}</td>
      </tr>
    </>
  );
}

function BuyDialog({
  chain,
  pick,
  lots,
  maxLots,
  busy,
  notice,
  heldUnits,
  heldAvg,
  canSell,
  onLots,
  onRight,
  onClose,
  onOrder,
}: {
  chain: Chain;
  pick: Pick;
  lots: number;
  maxLots: number;
  busy: boolean;
  notice: string;
  heldUnits: number;
  heldAvg: number | null;
  canSell: boolean;
  onLots: (lots: number) => void;
  onRight: (right: "CE" | "PE") => void;
  onClose: () => void;
  onOrder: (side: "buy" | "sell") => void;
}) {
  const row = chain.rows.find((item) => item.strike === pick.strike);
  const call = row?.call;
  const put = row?.put;
  const leg = pick.right === "CE" ? call : put;
  const lotSize = chain.lot_size || 0;
  const units = lotSize * lots;
  const premium = leg?.ltp ?? null;
  const ready = Boolean(leg?.trading_symbol && premium != null && premium > 0);
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="buy-title" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div id="buy-title" className="text-lg font-semibold">Buy {num(pick.strike, 0)} {pick.right === "CE" ? "call" : "put"}</div>
            <p className="text-sm text-mute">{leg?.trading_symbol || chain.name}</p>
          </div>
          <button className="ghost" type="button" onClick={onClose}>Close</button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <SideButton label="Call" leg={call} active={pick.right === "CE"} onClick={() => onRight("CE")} />
          <SideButton label="Put" leg={put} active={pick.right === "PE"} onClick={() => onRight("PE")} />
        </div>
        <p className="mt-3 text-sm text-mute">
          {ready
            ? `${lots} lot = ${units} units. About ₹${num((premium as number) * units)} before slippage and the paper brokerage.`
            : "This side has no Upstox premium, so it cannot be bought."}
          {heldUnits > 0 ? ` Open ${heldUnits} units at ₹${num(heldAvg)}.` : ""}
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="grid gap-1 text-xs text-mute">Lots
            <input
              type="number"
              min={1}
              max={maxLots}
              value={lots}
              autoFocus
              onChange={(event) => onLots(Math.max(1, Math.min(maxLots, Number(event.target.value) || 1)))}
            />
          </label>
          <button type="button" disabled={!ready || busy} onClick={() => onOrder("buy")}>Buy</button>
          <button className="ghost" type="button" disabled={!ready || busy || !canSell} onClick={() => onOrder("sell")}>Sell</button>
        </div>
        {!canSell && <p className="mt-2 text-xs text-mute">Sell closes a paper long. Buy the contract before selling it.</p>}
        {notice && <p className="mt-3 text-sm">{notice}</p>}
        <p className="mt-3 text-xs text-mute">Paper fill from the Upstox premium. Live orders stay off.</p>
      </div>
    </div>
  );
}

function SideButton({ label, leg, active, onClick }: { label: string; leg?: Leg | null; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className="ghost text-left" style={active ? { borderColor: "var(--primary)" } : undefined} onClick={onClick}>
      <span className="block text-xs text-mute">{label}</span>
      <span className="block text-base font-semibold">{leg?.ltp != null && leg.ltp > 0 ? `₹${num(leg.ltp)}` : "—"}</span>
    </button>
  );
}

function PremiumCell({
  leg,
  right,
  strike,
  pick,
  onStrike,
  klass,
}: {
  leg: Leg | null;
  right: "CE" | "PE";
  strike: number;
  pick: Pick | null;
  onStrike: (strike: number, right?: "CE" | "PE") => void;
  klass: string;
}) {
  const pct = changePct(leg?.ltp ?? null, leg?.close ?? null);
  const selected = pick?.right === right && pick.strike === strike;
  return (
    <td className={klass}>
      {leg?.ltp != null && leg.ltp > 0 && leg.trading_symbol ? (
        <button
          type="button"
          className="chain-hit ghost"
          data-on={selected}
          onClick={() => onStrike(strike, right)}
        >
          {num(leg.ltp)}
        </button>
      ) : (
        <span>{leg?.ltp == null ? "—" : num(leg.ltp)}</span>
      )}
      {pct != null && <div className={tone(pct)}>{signed(pct)}</div>}
    </td>
  );
}

function OiCell({ leg, klass }: { leg: Leg | null; klass: string }) {
  const pct = changePct(leg?.oi ?? null, leg?.prev_oi ?? null);
  return (
    <td className={klass}>
      <div>{leg?.oi == null ? "—" : Math.round(leg.oi).toLocaleString("en-IN")}</div>
      {pct != null && <div className={tone(pct)}>{signed(pct)}</div>}
    </td>
  );
}

function visibleRows(chain: Chain | null, showAll: boolean) {
  if (!chain) return [];
  if (showAll || chain.spot == null || chain.rows.length <= 25) return chain.rows;
  let atm = 0;
  for (let i = 1; i < chain.rows.length; i += 1) {
    if (Math.abs(chain.rows[i].strike - chain.spot) < Math.abs(chain.rows[atm].strike - chain.spot)) atm = i;
  }
  return chain.rows.slice(Math.max(0, atm - 12), atm + 13);
}

function changePct(value: number | null, base: number | null) {
  if (value == null || base == null || base === 0) return null;
  return ((value - base) / base) * 100;
}

function signed(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function fixed(value: number | null, digits: number) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function expiryLabel(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
