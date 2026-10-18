"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, token } from "@/lib/api";
import { listedLogoUrl } from "@/lib/logos";

type Hit = {
  symbol: string;
  name?: string | null;
  exchange: string;
  exchanges?: string[];
};

export function TopSearch() {
  const router = useRouter();
  const path = usePathname();
  const wrap = useRef<HTMLDivElement>(null);
  const seq = useRef(0);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setQuery("");
    setOpen(false);
  }, [path]);

  useEffect(() => {
    function onDoc(event: MouseEvent) {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    const q = query.trim();
    const id = ++seq.current;
    if (q.length < 1) {
      setHits([]);
      setNote("");
      setBusy(false);
      setOpen(false);
      return;
    }
    if (!token()) {
      setHits([]);
      setBusy(false);
      setNote("Sign in to search stocks.");
      setOpen(true);
      return;
    }
    setBusy(true);
    const handle = window.setTimeout(() => {
      api<{ results: Hit[] }>(`/api/v1/market/search?q=${encodeURIComponent(q)}`)
        .then((body) => {
          if (seq.current !== id) return;
          setHits(body.results);
          setNote(body.results.length === 0 ? "No matching NSE or BSE symbol." : "");
          setActive(0);
          setBusy(false);
          setOpen(true);
        })
        .catch((err: Error) => {
          if (seq.current !== id) return;
          setHits([]);
          setBusy(false);
          setNote(err.message || "Search failed.");
          setOpen(true);
        });
    }, 160);
    return () => window.clearTimeout(handle);
  }, [query]);

  function go(symbol: string, exchange = "NSE") {
    setOpen(false);
    setQuery("");
    router.push(`/research?symbol=${encodeURIComponent(symbol)}&exchange=${encodeURIComponent(exchange)}`);
  }

  return (
    <div ref={wrap} className="relative min-w-0 flex-1">
      <form
        className="suggest-field"
        onSubmit={(event) => {
          event.preventDefault();
          if (open && hits[active]) {
            go(hits[active].symbol, hits[active].exchange);
            return;
          }
          const next = query.trim().toUpperCase();
          if (next) go(next);
        }}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
          <circle cx="7" cy="7" r="4.25" stroke="currentColor" strokeWidth="1.6" />
          <path d="M10.5 10.5 14 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => {
            if (query.trim()) setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
              return;
            }
            if (!open || hits.length === 0) return;
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((index) => Math.min(index + 1, hits.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((index) => Math.max(index - 1, 0));
            }
          }}
          placeholder="What are you looking for today?"
          aria-label="Search a symbol"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls="stock-search-results"
          autoComplete="off"
        />
      </form>
      {open && (
        <div className="suggest-panel" id="stock-search-results" role="listbox">
          <div className="suggest-label">{busy ? "Searching" : "Stocks"}</div>
          {hits.map((hit, index) => {
            const exchanges = hit.exchanges?.length ? hit.exchanges : [hit.exchange];
            const title = hit.name || hit.symbol;
            return (
              <div
                key={hit.symbol}
                className="suggest-row"
                role="option"
                aria-selected={index === active}
                data-active={index === active}
                onMouseEnter={() => setActive(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => go(hit.symbol, hit.exchange)}
              >
                <Mark symbol={hit.symbol} exchange={hit.exchange} label={title} />
                <span className="min-w-0">
                  <span className="block truncate">{highlight(title, query)}</span>
                  <span className="suggest-symbol">{highlight(hit.symbol, query)}</span>
                </span>
                <span className="suggest-exchanges">
                  {exchanges.map((exchange) => <span key={exchange}>{exchange}</span>)}
                </span>
              </div>
            );
          })}
          {hits.length === 0 && !busy && note && <div className="px-3 py-2 text-sm text-mute">{note}</div>}
          {hits.length > 0 && <div className="suggest-hint">↑↓ to move · Enter to open</div>}
        </div>
      )}
    </div>
  );
}

function Mark({ symbol, exchange, label }: { symbol: string; exchange: string; label: string }) {
  const [failed, setFailed] = useState(false);
  const letter = label.replace(/[^A-Za-z0-9]/g, "").slice(0, 1).toUpperCase() || "?";
  return (
    <span className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-xl border border-[var(--line)] bg-white text-sm font-bold text-[var(--primary)]">
      {failed ? letter : <img src={listedLogoUrl(symbol, exchange)} alt="" className="h-7 w-7 object-contain" onError={() => setFailed(true)} />}
    </span>
  );
}

function highlight(text: string, query: string) {
  const needle = query.trim();
  const at = text.toLowerCase().indexOf(needle.toLowerCase());
  if (!needle || at < 0) return text;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + needle.length)}</mark>
      {text.slice(at + needle.length)}
    </>
  );
}
