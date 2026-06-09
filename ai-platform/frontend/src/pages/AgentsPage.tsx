import { useEffect, useState } from "react";
import { api, AgentInfo } from "../services/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);

  useEffect(() => {
    api.agents().then((r) => setAgents(r.agents));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Agents</h1>
      {agents.length === 0 ? (
        <p className="text-gray-500">Loading…</p>
      ) : (
        <div className="grid gap-4">
          {agents.map((a) => (
            <div key={a.name} className="bg-white rounded shadow p-4">
              <h2 className="font-semibold">{a.name}</h2>
              <p className="text-sm text-gray-500">{a.type}</p>
              <p className="mt-1 text-gray-700">{a.description}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
