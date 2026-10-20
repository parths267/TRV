"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const message = sessionStorage.getItem("stoxs8_notice");
    if (!message) return;
    sessionStorage.removeItem("stoxs8_notice");
    setNotice(message);
  }, []);

  return (
    <form
      className="panel mx-auto grid max-w-md gap-3 p-6"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        try {
          const body = await api<{ access_token: string }>("/api/v1/auth/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
          });
          setToken(body.access_token);
          router.push("/");
        } catch (err) {
          setError(err instanceof Error ? err.message : "Login failed");
        }
      }}
    >
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-sm text-mute">Your research board, paper book, and alerts.</p>
      </div>
      <label className="grid gap-1 text-sm font-medium">Email
        <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="username" required />
      </label>
      <label className="grid gap-1 text-sm font-medium">Password
        <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required />
      </label>
      {notice && <p className="text-sm text-mute">{notice}</p>}
      {error && <p className="text-sm text-down">{error}</p>}
      <button type="submit">Sign in</button>
      <Link href="/register" className="text-sm text-mute">Create an account</Link>
    </form>
  );
}
