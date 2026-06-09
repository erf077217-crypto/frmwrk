const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.statusText}`);
  return res.json();
}

// ── Types ─────────────────────────────────────────────────

export interface Health {
  status: string;
  version: string;
  app_name: string;
  diagnostics?: { provider_health?: Record<string, string> };
}

export interface ProviderInfo {
  name: string;
  display_name: string;
  streaming: boolean;
  tools: boolean;
}

export interface ProviderStatus {
  name: string;
  display_name: string;
  status: string;
  message: string;
  model: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  created: string;
}

export interface AgentInfo {
  name: string;
  type: string;
  description: string;
}

export interface ToolInfo {
  name: string;
  description: string;
}

export interface ChatRequest {
  provider: string;
  model?: string;
  messages: { role: string; content: string }[];
  stream?: boolean;
  temperature?: number;
  max_tokens?: number;
}

export interface ChatResponse {
  content: string;
  model: string;
  usage: { prompt_tokens: number; completion_tokens: number };
  provider: string;
}

// ── API Methods ───────────────────────────────────────────

export const api = {
  health: () => get<Health>("/health"),
  providers: () => get<{ providers: ProviderInfo[] }>("/providers"),
  providerStatus: () => get<{ providers: ProviderStatus[] }>("/providers/status"),
  providerModels: (name: string) => get<{ provider: string; models: ModelInfo[] }>(`/providers/${name}/models`),
  providerHealth: (name: string) => get<ProviderStatus>(`/providers/${name}/health`),
  agents: () => get<{ agents: AgentInfo[] }>("/agents"),
  tools: () => get<{ tools: ToolInfo[] }>("/tools"),
  chat: (req: ChatRequest) => post<ChatResponse>("/chat", req),
};

// ── Streaming Helpers ─────────────────────────────────────

export function chatStream(
  req: ChatRequest,
  onChunk: (text: string) => void,
  onDone: (model?: string) => void,
  onError: (err: string) => void,
  signal?: AbortSignal
): () => void {
  const controller = new AbortController();
  const combinedSignal = signal
    ? AbortSignal.any?.([signal, controller.signal]) ?? controller.signal
    : controller.signal;

  fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, stream: true }),
    signal: combinedSignal,
  })
    .then(async (res) => {
      if (!res.ok) {
        onError(`HTTP ${res.status}: ${res.statusText}`);
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) {
        onError("No response body");
        return;
      }
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            const event = line.slice(7).trim();
            if (event === "done") {
              // next line has data
              continue;
            }
          }
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                onChunk(data.content);
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError(err.message);
      }
    });

  return () => controller.abort();
}
