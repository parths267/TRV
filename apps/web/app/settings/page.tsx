"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Me = { email: string; name: string; plan: string; theme: string; quiet_start?: string | null; quiet_end?: string | null; telegram_chat_id?: string | null; email_verified: boolean };

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api<Me>("/api/v1/auth/me").then(setMe).catch((err: Error) => setMessage(err.message));
  }, []);

  function applyTheme(theme: string) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("bazaar_theme", theme);
  }

  if (!me) return <p className="text-mute">{message || "Loading profile…"}</p>;

  return (
    <form className="panel grid max-w-xl gap-3 p-4" onSubmit={async (event) => {
      event.preventDefault();
      const saved = await api<Me>("/api/v1/auth/me", { method: "PATCH", body: JSON.stringify(me) });
      setMe(saved);
      applyTheme(saved.theme);
      setMessage("Saved.");
    }}>
      <h1 className="text-xl font-semibold">Settings</h1>
      <p className="text-sm text-mute">{me.email} · {me.plan} plan · verified {me.email_verified ? "yes" : "no"}</p>
      <label className="grid gap-1 text-sm">Name<input value={me.name} onChange={(event) => setMe({ ...me, name: event.target.value })} /></label>
      <label className="grid gap-1 text-sm">Theme
        <select value={me.theme} onChange={(event) => setMe({ ...me, theme: event.target.value })}>
          <option value="dark">Dark</option>
          <option value="light">Light</option>
        </select>
      </label>
      <label className="grid gap-1 text-sm">Quiet hours start<input placeholder="22:00" value={me.quiet_start || ""} onChange={(event) => setMe({ ...me, quiet_start: event.target.value })} /></label>
      <label className="grid gap-1 text-sm">Quiet hours end<input placeholder="08:00" value={me.quiet_end || ""} onChange={(event) => setMe({ ...me, quiet_end: event.target.value })} /></label>
      <label className="grid gap-1 text-sm">Telegram chat id<input value={me.telegram_chat_id || ""} onChange={(event) => setMe({ ...me, telegram_chat_id: event.target.value })} /></label>
      <button type="submit">Save</button>
      {message && <p className="text-sm text-mute">{message}</p>}
      <p className="text-xs text-mute">Email and Telegram send only when the server has SMTP or a bot token. Billing is not connected. An admin changes plans.</p>
    </form>
  );
}
