"use client";

import { useEffect, useMemo, useState } from "react";
import { PageHead } from "@/components/PageHead";
import { Failure, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { listedLogoUrl } from "@/lib/logos";

type Result = {
  symbol: string;
  company?: string | null;
  purpose: string;
  detail?: string | null;
  date: string;
  source_url: string;
};

type Payload = {
  status: string;
  reason?: string;
  count: number;
  results: Result[];
  window?: { from: string; to: string };
  source_url?: string;
  universe_note?: string;
};

const AVATAR = ["#6C5CE7", "#5B6CFF", "#F5A524", "#E67E22", "#00B386", "#0EA5A0", "#8B5CF6", "#EC4899"];

export default function ResultsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState<Payload | null>(null);
  const [query, setQuery] = useState("");

  function load() {
    setLoading(true);
    setError("");
    api<Payload>("/api/v1/results")
      .then(setData)
      .catch((err: Error) => setError(err.message || "Results request failed"))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const source = (data?.results || []).filter((row) =>
      !needle || [row.symbol, row.company, row.purpose, row.detail, row.date].some((value) =>
        String(value || "").toLowerCase().includes(needle),
      ),
    );
    const grouped = new Map<string, Result[]>();
    for (const row of source) {
      const list = grouped.get(row.date) || [];
      list.push(row);
      grouped.set(row.date, list);
    }
    return [...grouped.entries()];
  }, [data, query]);

  const shown = groups.reduce((sum, [, rows]) => sum + rows.length, 0);

  return (
    <div className="grid min-w-0 gap-4">
      <section className="panel p-4">
        <PageHead
          kicker="Market"
          title="Corporate results"
          lede="Upcoming financial results for the top 250 companies, Nifty 100 and Nifty Midcap 150. The date is the board meeting the company has told the exchange about."
          aside={data?.status === "ok" ? (
            <div className="stat text-right">
              <strong>{shown}</strong>
              <span>results in the top 250</span>
            </div>
          ) : null}
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search company or symbol"
            aria-label="Search upcoming results"
          />
          <button className="ghost w-fit" type="button" onClick={load}>Refresh</button>
          {data?.source_url && (
            <a className="text-sm" style={{ color: "var(--primary)" }} href={data.source_url} target="_blank" rel="noreferrer">
              NSE event calendar
            </a>
          )}
        </div>
        {data?.window && (
          <p className="mt-2 text-xs text-mute">
            {labelDate(data.window.from)} – {labelDate(data.window.to)}
            {data.universe_note ? `. ${data.universe_note}` : ""}
          </p>
        )}
      </section>
      {loading && <Loading label="Reading the NSE result calendar" />}
      {error && <Failure error={error} onRetry={load} />}
      {data && data.status !== "ok" && data.status !== "demo" && (
        <section className="panel p-4">
          <h2 className="font-semibold">Calendar unavailable</h2>
          <p className="mt-1 text-sm text-mute">{data.reason}</p>
        </section>
      )}
      {data && !loading && data.status !== "unavailable" && groups.length === 0 && (
        <section className="panel p-6 text-sm text-mute">
          {query ? "No company matches that search." : "The calendar returned no upcoming financial results."}
        </section>
      )}
      {groups.map(([date, rows]) => (
        <section key={date} className="result-day">
          <DateMark iso={date} count={rows.length} />
          <div className="result-list">
            {rows.map((row) => (
              <article key={`${row.symbol}-${row.date}-${row.purpose}`} className="result-row">
                <Mark symbol={row.symbol} company={row.company} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-semibold">{row.company || row.symbol}</div>
                      <div className="text-xs font-semibold tracking-wide text-mute">{row.symbol}</div>
                    </div>
                    <div className="flex flex-wrap justify-end gap-1">
                      {row.purpose.split("/").map((part) => (
                        <span key={part} className="result-chip" data-tone={part.toLowerCase().includes("result") ? "result" : "other"}>
                          {part}
                        </span>
                      ))}
                    </div>
                  </div>
                  {row.detail && <p className="mt-1 text-sm leading-5 text-mute">{row.detail}</p>}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function DateMark({ iso, count }: { iso: string; count: number }) {
  const [year, month, day] = iso.split("-").map(Number);
  const when = year && month && day ? new Date(Date.UTC(year, month - 1, day)) : null;
  const label = (options: Intl.DateTimeFormatOptions) => when
    ? when.toLocaleDateString("en-IN", { ...options, timeZone: "UTC" })
    : iso;
  return (
    <div className="result-date">
      <span>{label({ month: "short" })}</span>
      <strong>{label({ day: "numeric" })}</strong>
      <span>{label({ weekday: "short" })} · {count}</span>
    </div>
  );
}

function Mark({ symbol, company }: { symbol: string; company?: string | null }) {
  const [failed, setFailed] = useState(false);
  const letter = (company || symbol).replace(/[^A-Za-z0-9]/g, "").slice(0, 1).toUpperCase() || "?";
  let hash = 0;
  for (const ch of symbol) hash = (hash + ch.charCodeAt(0)) % AVATAR.length;
  if (failed) {
    return (
      <span className="grid h-10 w-10 place-items-center rounded-2xl text-sm font-semibold text-white" style={{ background: AVATAR[hash] }}>
        {letter}
      </span>
    );
  }
  return (
    <span className="grid h-10 w-10 place-items-center overflow-hidden rounded-2xl border border-[var(--line)] bg-white">
      <img src={listedLogoUrl(symbol)} alt="" className="h-7 w-7 object-contain" loading="lazy" onError={() => setFailed(true)} />
    </span>
  );
}

function labelDate(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
