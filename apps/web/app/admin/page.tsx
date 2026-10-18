"use client";

import { useEffect, useState } from "react";
import { Failure } from "@/components/States";
import { api } from "@/lib/api";

type Row = { id: string; email: string; plan: string; role: string };

export default function AdminPage() {
  const [users, setUsers] = useState<Row[]>([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      const body = await api<{ users: Row[] }>("/api/v1/admin/users");
      setUsers(body.users);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Admin request failed");
    }
  }
  useEffect(() => { load(); }, []);

  return (
    <div className="grid gap-4">
      <section className="panel p-4">
        <h1 className="text-xl font-semibold">Plans</h1>
        <p className="text-sm text-mute">Changing a plan does not charge a card. Quotas are enforced by the API.</p>
        <table className="mt-3">
          <thead><tr><th>Email</th><th>Role</th><th>Plan</th></tr></thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.email}</td>
                <td>{user.role}</td>
                <td>
                  <select value={user.plan} onChange={async (event) => {
                    await api(`/api/v1/admin/users/${user.id}/plan`, { method: "PATCH", body: JSON.stringify({ plan: event.target.value }) });
                    load();
                  }}>
                    {["free", "pro", "premium"].map((plan) => <option key={plan}>{plan}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {error && <Failure error={error} />}
    </div>
  );
}
