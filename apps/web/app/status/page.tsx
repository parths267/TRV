"use client";

import { useEffect, useState } from "react";
import { Failure, Loading } from "@/components/States";
import { api, token } from "@/lib/api";

export default function StatusPage() {
  const [body, setBody] = useState<string>("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token()) {
      setLoading(false);
      setError("Sign in to read provider status.");
      return;
    }
    api("/api/v1/market/status")
      .then((payload) => setBody(JSON.stringify(payload, null, 2)))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading label="Checking providers" />;
  if (error) return <Failure error={error} />;
  return (
    <section className="panel p-4">
      <h1 className="text-xl font-semibold">Provider status</h1>
      <pre className="mt-3 overflow-auto text-xs">{body}</pre>
    </section>
  );
}
