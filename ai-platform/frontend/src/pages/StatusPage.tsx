import { useEffect, useState } from "react";
import { api, ToolInfo } from "../services/api";

export default function StatusPage() {
  const [tools, setTools] = useState<ToolInfo[]>([]);

  useEffect(() => {
    api.tools().then((r) => setTools(r.tools));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">System Status</h1>

      <section className="mb-6">
        <h2 className="text-lg font-semibold mb-2">Registered Tools</h2>
        {tools.length === 0 ? (
          <p className="text-gray-500">Loading…</p>
        ) : (
          <table className="w-full bg-white rounded shadow">
            <thead>
              <tr className="border-b text-left text-sm text-gray-500">
                <th className="p-3">Name</th>
                <th className="p-3">Description</th>
              </tr>
            </thead>
            <tbody>
              {tools.map((t) => (
                <tr key={t.name} className="border-b">
                  <td className="p-3 font-medium">{t.name}</td>
                  <td className="p-3 text-gray-600">{t.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
