# Architecture

## System Overview

```
┌─ Host / Orchestrator ─────────────────────────────────────┐
│                                                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐     │
│  │  nginx   │───▶│  FastAPI │───▶│  Providers       │     │
│  │ frontend │    │  backend │    │  ─ OpenAI        │     │
│  │ :80      │    │  :8000   │    │  ─ Anthropic     │     │
│  │          │    │          │    │  ─ Gemini        │     │
│  │  React   │    │  Agents  │    │  ─ Ollama        │     │
│  │  (built) │    │  Tools   │    └──────────────────┘     │
│  └──────────┘    └──────────┘                              │
│       │               │                                    │
│       └─────── /api ───┘                                    │
│                                                            │
│  ┌──────────────────────────────────────────────────┐      │
│  │  Configuration (env / .env)                      │      │
│  └──────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────┘
```

The platform uses a **container-first architecture**. Every component
runs in a Docker container. No local Python or Node installation is
required beyond Docker itself.

## Container Architecture

```
docker-compose.yml
├── backend
│   ├── docker/backend.Dockerfile  (multi-stage: builder + runtime)
│   ├── Python 3.12-slim
│   ├── Port 8000
│   ├── Health: GET /health
│   └── Environment: .env
│
├── frontend
│   ├── docker/frontend.Dockerfile (multi-stage: builder + nginx)
│   ├── Node 22 (build), nginx (runtime)
│   ├── Port 80
│   ├── Proxies /api/* → backend:8000
│   └── SPA fallback → index.html
│
└── network: ai-platform (bridge)
```

**Multi-stage builds:**
- **Builder stage** installs all dependencies and compiles artifacts.
- **Runtime stage** copies only what is needed — keeping images small.

**Health checks:**
- Backend: `curl --fail http://localhost:8000/health`
- Frontend: `wget --spider http://localhost:80/`
- Compose `depends_on` with `condition: service_healthy` ensures
  correct startup order.

## Deployment Model

### Docker Compose (default)

```bash
docker compose up
# Backend  → http://localhost:8000
# Frontend → http://localhost:80
```

No additional setup required. Copy `.env.example` to `.env` and
add API keys for the providers you want to use.

### Kubernetes (future)

Each container maps directly to a Kubernetes Deployment:
- `backend` Deployment + Service (port 8000)
- `frontend` Deployment + Service (port 80)
- Ingress to route `/api/*` to backend and `/*` to frontend

### On-Premise / Air-Gapped

- Pre-build images and push to an internal registry.
- Use `.env` for all configuration — no hardcoded secrets.
- Ollama can run on the same host (accessed via `host.docker.internal`).

## Provider Model

```
BaseProvider (abstract)
├── OpenAIProvider    (gpt-4o, …)
├── ClaudeProvider    (claude-3-opus, …)
├── GeminiProvider    (gemini-1.5-pro, …)
└── OllamaProvider    (llama3, …)
```

Every provider implements:
- `initialize()` / `cleanup()` — lifecycle management
- `complete(messages, **kwargs)` — chat completion
- `supports_streaming()` / `supports_tools()` — capability flags

Providers are registered by name in `ProviderRegistry` and
looked up at runtime. The calling code never imports a concrete
provider directly.

## Agent Model

```
BaseAgent (abstract)
├── CodingAgent
├── DocumentationAgent
└── TestingAgent
```

Every agent follows:
- `initialize()` — load prompts, validate configuration
- `run(task)` — execute the agent's core logic
- `complete()` — finalize and return results
- `cleanup()` — release resources

Agents receive a `BaseProvider` for LLM access and a `ToolRegistry`
for tool access.

## Tool Model

```
BaseTool (abstract)
├── FileTool       (read / write / delete files)
├── DirectoryTool  (list / create / remove directories)
├── GitTool        (git status, diff, log, commit)
├── ShellTool      (arbitrary shell commands)
└── DatabaseTool   (SQL queries)
```

Each tool declares:
- `name` — unique identifier
- `description` — human-readable summary
- `parameters` — JSON Schema for input validation

Tools are registered in the central `ToolRegistry` at startup.

## Configuration

All configuration is environment-driven via Pydantic `BaseSettings`:

| Variable              | Purpose                       |
|-----------------------|-------------------------------|
| `OPENAI_API_KEY`      | OpenAI authentication         |
| `ANTHROPIC_API_KEY`   | Anthropic authentication      |
| `GEMINI_API_KEY`      | Google Gemini auth            |
| `OLLAMA_BASE_URL`     | Local Ollama server URL       |
| `LOG_LEVEL`           | Logging verbosity             |
| `LOG_JSON`            | Structured JSON logging flag  |
| `DEBUG`               | Development mode toggle       |
| `PORT` / `HOST`       | Server binding                |

**Structured logging** — when `LOG_JSON=true`, the backend outputs
newline-delimited JSON logs suitable for ingestion by Loki,
Elasticsearch, or similar.

## Startup Diagnostics

On every boot the backend:
1. Prints a startup banner with version and config summary.
2. Validates that required environment variables are set.
3. Logs the status of every provider (enabled / disabled + key presence).
4. Reports any warnings on the `/health` endpoint.

## Future Roadmap

| Phase | Focus                          |
|-------|--------------------------------|
| 1     | Containerized foundation       |
| 2     | Multi-provider completions     |
| 3     | Agent workflows & RAG          |
| 4     | Approval workflows & security  |
| 5     | Enterprise integrations        |

## Project Structure

```
ai-platform/
├── docker/           # Dockerfiles and nginx config
├── backend/          # FastAPI application server
├── frontend/         # React + Vite web UI
├── agents/           # Agent runtime and definitions
├── providers/        # LLM provider abstractions
├── tools/            # Tool framework and built-in tools
├── workflows/        # Workflow orchestration (future)
├── knowledge/        # Knowledge base / RAG (future)
├── security/         # Auth, approval workflows (future)
├── configs/          # Configuration management
├── tests/            # Unit and integration tests
├── docs/             # Architecture and user documentation
├── docker-compose.yml
└── .env.example
```
