"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

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
      <h1 className="text-xl font-semibold">Sign in</h1>
      <input value={email} onChange={(event) => setEmail(event.target.value)} type="text" placeholder="Username" autoComplete="username" required />
      <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="Password" required />
      {error && <p className="text-sm text-down">{error}</p>}
      <button type="submit">Sign in</button>
      <Link href="/register" className="text-sm text-mute">Create an account</Link>
    </form>
  );
}
