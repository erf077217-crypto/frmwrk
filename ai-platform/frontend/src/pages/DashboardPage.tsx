import { useEffect, useState } from "react";
import { api, Health } from "../services/api";

export default function DashboardPage() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded shadow p-4">
          <h2 className="text-sm text-gray-500 uppercase">Status</h2>
          <p className="text-xl font-semibold">{health?.status ?? "…"}</p>
        </div>
        <div className="bg-white rounded shadow p-4">
          <h2 className="text-sm text-gray-500 uppercase">Version</h2>
          <p className="text-xl font-semibold">{health?.version ?? "…"}</p>
        </div>
        <div className="bg-white rounded shadow p-4">
          <h2 className="text-sm text-gray-500 uppercase">Application</h2>
          <p className="text-xl font-semibold">{health?.app_name ?? "…"}</p>
        </div>
      </div>
      <p className="mt-6 text-gray-500 text-sm">
        Phase 1 — Foundation only. No AI workflows or agents active yet.
      </p>
    </div>
  );
}
