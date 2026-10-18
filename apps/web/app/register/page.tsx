"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [verify, setVerify] = useState("");

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
          setToken(body.access_token);
          if (body.verification_token) {
            await api("/api/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ token: body.verification_token }) });
            setVerify("Email marked verified with the development token.");
          }
          router.push("/");
        } catch (err) {
          setError(err instanceof Error ? err.message : "Registration failed");
        }
      }}
    >
      <h1 className="text-xl font-semibold">Create account</h1>
      <p className="text-sm text-mute">Free plan. Password needs at least 10 characters. No payment is collected.</p>
      <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" />
      <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" placeholder="Email" required />
      <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="Password" required />
      {error && <p className="text-sm text-down">{error}</p>}
      {verify && <p className="text-sm text-mute">{verify}</p>}
      <button type="submit">Register</button>
    </form>
  );
}
