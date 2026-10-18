"use client";

import { useState } from "react";
import { Failure, Loading } from "@/components/States";
import { api } from "@/lib/api";

type Deal = {
  symbol?: string;
  company?: string | null;
  category: string;
  client_name?: string | null;
  side?: string | null;
  quantity?: number | null;
  price?: number | null;
  value?: number | null;
  published_at?: string | null;
  source_url?: string;
  verification_status?: string;
  subject?: string | null;
};

type Payload = {
  status: string;
  reason?: string;
  note?: string;
  data_mode?: string;
  bulk_deals: Deal[];
  block_deals: Deal[];
  announcements: Deal[];
  official_pages?: Record<string, string>;
};

export default function DealsPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<Payload | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setData(await api<Payload>("/api/v1/events"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Events request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-4">
      <section className="panel p-4">
        <h1 className="text-xl font-semibold">Bulk deals, block deals, announcements</h1>
        <p className="text-sm text-mute">Rows are shown only when a source returns them. Bulk and block are separate feeds. A missing client name stays blank.</p>
        <button className="mt-3" type="button" onClick={load}>Load disclosures</button>
      </section>
      {loading && <Loading label="Asking the disclosure provider" />}
      {error && <Failure error={error} onRetry={load} />}
      {data && (
        <>
          {data.status !== "ok" && data.status !== "demo" && (
            <section className="panel p-4">
              <h2>Provider unavailable</h2>
              <p className="text-sm">{data.reason}</p>
            </section>
          )}
          {data.note && <p className="text-sm text-gold">{data.note}</p>}
          <DealTable title="Bulk deals" rows={data.bulk_deals} />
          <DealTable title="Block deals" rows={data.block_deals} />
          <DealTable title="Announcements" rows={data.announcements} />
          {data.official_pages && (
            <ul className="text-sm">
              {Object.entries(data.official_pages).map(([key, url]) => (
                <li key={key}><a href={url} target="_blank" rel="noreferrer">{key}</a></li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function DealTable({ title, rows }: { title: string; rows: Deal[] }) {
  return (
    <section className="panel p-4">
      <h2>{title}</h2>
      {rows.length === 0 ? <p className="text-sm text-mute">No rows from this source.</p> : (
        <table>
          <thead><tr><th>Symbol</th><th>Category</th><th>Client</th><th>Qty / price</th><th>Status</th></tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.symbol}-${index}`}>
                <td>{row.symbol || "—"}<div className="text-xs text-mute">{row.company || row.subject}</div></td>
                <td>{row.category} {row.side || ""}</td>
                <td>{row.client_name || "Not disclosed"}</td>
                <td className="font-mono">{row.quantity ?? "—"} @ {row.price ?? "—"}</td>
                <td className="text-xs"><a href={row.source_url} target="_blank" rel="noreferrer">{row.verification_status}</a><div>{row.published_at}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
