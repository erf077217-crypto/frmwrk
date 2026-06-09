import { useEffect, useState } from "react";
import { api, ProviderInfo } from "../services/api";

export default function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);

  useEffect(() => {
    api.providers().then((r) => setProviders(r.providers));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Providers</h1>
      {providers.length === 0 ? (
        <p className="text-gray-500">Loading…</p>
      ) : (
        <table className="w-full bg-white rounded shadow">
          <thead>
            <tr className="border-b text-left text-sm text-gray-500">
              <th className="p-3">Name</th>
              <th className="p-3">Streaming</th>
              <th className="p-3">Tools</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.name} className="border-b">
                <td className="p-3 font-medium">{p.display_name}</td>
                <td className="p-3">{p.streaming ? "✓" : "✗"}</td>
                <td className="p-3">{p.tools ? "✓" : "✗"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
