import { useEffect, useRef, useState } from "react";
import { api, ModelInfo, ProviderInfo, chatStream } from "../services/api";

export default function PlaygroundPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [streaming, setStreaming] = useState(true);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    api.providers().then((r) => {
      setProviders(r.providers);
      if (r.providers.length > 0) {
        setSelectedProvider(r.providers[0].name);
      }
    });
  }, []);

  useEffect(() => {
    if (!selectedProvider) return;
    setModels([]);
    setSelectedModel("");
    api
      .providerModels(selectedProvider)
      .then((r) => {
        setModels(r.models);
        if (r.models.length > 0) {
          setSelectedModel(r.models[0].id);
        }
      })
      .catch(() => {
        setModels([
          { id: "gpt-4o", name: "gpt-4o", created: "" },
          { id: "gpt-4o-mini", name: "gpt-4o-mini", created: "" },
        ]);
      });
  }, [selectedProvider]);

  const handleSubmit = async () => {
    if (!selectedProvider || !prompt.trim()) return;
    setLoading(true);
    setResponse("");
    setError("");

    const messages = [{ role: "user" as const, content: prompt }];

    if (streaming) {
      cancelRef.current = chatStream(
        {
          provider: selectedProvider,
          model: selectedModel || undefined,
          messages,
        },
        (chunk) => setResponse((prev) => prev + chunk),
        () => setLoading(false),
        (err) => {
          setError(err);
          setLoading(false);
        }
      );
    } else {
      try {
        const result = await api.chat({
          provider: selectedProvider,
          model: selectedModel || undefined,
          messages,
        });
        setResponse(result.content);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Request failed");
      } finally {
        setLoading(false);
      }
    }
  };

  const handleCancel = () => {
    cancelRef.current?.();
    cancelRef.current = null;
    setLoading(false);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Provider Playground</h1>

      <div className="bg-white rounded shadow p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
            <select
              className="w-full border rounded px-3 py-2"
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
            >
              <option value="">-- Select --</option>
              {providers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
            <select
              className="w-full border rounded px-3 py-2"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
            >
              <option value="">-- Default --</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Prompt</label>
          <textarea
            className="w-full border rounded px-3 py-2 min-h-[100px]"
            placeholder="Enter your prompt..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={streaming}
              onChange={(e) => setStreaming(e.target.checked)}
            />
            Stream response
          </label>

          <button
            className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50"
            onClick={handleSubmit}
            disabled={loading || !selectedProvider || !prompt.trim()}
          >
            {loading ? "Sending..." : "Send"}
          </button>

          {loading && (
            <button
              className="bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600"
              onClick={handleCancel}
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 mb-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      {response && (
        <div className="bg-white rounded shadow p-4">
          <h2 className="text-sm font-medium text-gray-500 uppercase mb-2">Response</h2>
          <pre className="whitespace-pre-wrap font-sans text-gray-800">{response}</pre>
        </div>
      )}
    </div>
  );
}
