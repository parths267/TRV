"use client";

import { useEffect, useState } from "react";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";

type Alert = { id: string; name: string; kind: string; cooldown_seconds: number };
type Note = { id: string; title: string; body: string; created_at: string; read: boolean };

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [symbol, setSymbol] = useState("RELIANCE");
  const [threshold, setThreshold] = useState(1000);
  const [error, setError] = useState("");

  async function load() {
    try {
      const [rules, inbox] = await Promise.all([
        api<{ alerts: Alert[] }>("/api/v1/alerts"),
        api<{ notifications: Note[] }>("/api/v1/notifications"),
      ]);
      setAlerts(rules.alerts);
      setNotes(inbox.notifications);
      if (typeof Notification !== "undefined" && Notification.permission === "granted" && inbox.notifications.some((note) => !note.read)) {
        new Notification("Stoxs8 alert", { body: inbox.notifications.find((note) => !note.read)?.body });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Alerts failed");
    }
  }
  useEffect(() => { load(); }, []);

  return (
    <div className="grid gap-4">
      <section className="panel p-4">
        <h1 className="text-xl font-semibold">Alerts</h1>
        <p className="text-sm text-mute">The API scheduler evaluates rules. This page does not have to stay open. The same fingerprint waits out its cooldown, then can fire again.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
          <input type="number" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
          <button type="button" onClick={async () => {
            await api("/api/v1/alerts", {
              method: "POST",
              body: JSON.stringify({
                name: `${symbol} at ${threshold}`,
                kind: "price",
                config: { symbol, operator: "gte", threshold },
                channels: ["in_app"],
                cooldown_seconds: 3600,
              }),
            });
            load();
          }}>Add price alert</button>
          <button className="ghost" type="button" onClick={async () => {
            if (typeof Notification !== "undefined") await Notification.requestPermission();
          }}>Enable browser notifications</button>
          <button className="ghost" type="button" onClick={async () => { await api("/api/v1/alerts/evaluate", { method: "POST" }); load(); }}>Evaluate now</button>
        </div>
        <ul className="mt-3 text-sm">{alerts.map((alert) => <li key={alert.id}>{alert.name} · {alert.kind} · cooldown {alert.cooldown_seconds}s</li>)}</ul>
      </section>
      <section className="panel p-4">
        <h2>Inbox</h2>
        {notes.length === 0 ? <p className="text-sm text-mute">No notifications.</p> : notes.map((note) => (
          <article key={note.id} className="border-b border-[var(--line)] py-2">
            <div className="font-medium">{note.title}</div>
            <p className="text-sm">{note.body}</p>
            <p className="text-xs text-mute">{new Date(note.created_at).toLocaleString("en-IN")}</p>
          </article>
        ))}
      </section>
      {error && <Failure error={error} onRetry={load} />}
    </div>
  );
}
