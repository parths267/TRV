"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  return (
    <form
      className="panel mx-auto grid max-w-md gap-3 p-6"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        try {
          const body = await api<{ access_token: string; verification_token?: string }>("/api/v1/auth/register", {
            method: "POST",
            body: JSON.stringify({ email, password, name }),
          });
          if (body.verification_token) {
            await api("/api/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ token: body.verification_token }) }).catch(() => undefined);
          }
          sessionStorage.setItem("stoxs8_notice", "Account created. Sign in with that email and password.");
          router.push("/login");
        } catch (err) {
          setError(err instanceof Error ? err.message : "Registration failed");
        }
      }}
    >
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Create account</h1>
        <p className="mt-1 text-sm text-mute">Free plan. Password needs at least 10 characters. No payment is collected.</p>
      </div>
      <label className="grid gap-1 text-sm font-medium">Name
        <input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" />
      </label>
      <label className="grid gap-1 text-sm font-medium">Email
        <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" required />
      </label>
      <label className="grid gap-1 text-sm font-medium">Password
        <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="new-password" required />
      </label>
      {error && <p className="text-sm text-down">{error}</p>}
      <button type="submit">Register</button>
    </form>
  );
}
