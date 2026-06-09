# Provider Layer

## Provider Architecture

```
┌──────────────────────────────────────────────────┐
│                  Application Code                 │
│  (agents, API clients, workflows)                │
├──────────────────────────────────────────────────┤
│               Provider Registry                   │
│  register_provider() → get_provider() → list()   │
├──────────────────────────────────────────────────┤
│              BaseProvider Interface               │
│  generate()  stream()  models()  health()        │
├──────────┬──────────┬──────────┬─────────────────┤
│  OpenAI   │  Claude  │  Gemini  │    Ollama       │
│ Provider  │ Provider │ Provider │   Provider      │
└──────────┴──────────┴──────────┴─────────────────┘
```

Application code never imports a concrete provider. It works
exclusively through the `BaseProvider` interface and the
`ProviderRegistry`.

## Provider Interface

Every provider implements `BaseProvider` (`providers/base.py`):

| Method           | Returns                            | Description                        |
|------------------|------------------------------------|------------------------------------|
| `generate()`     | `dict` (content, model, usage)     | Non-streaming chat completion      |
| `stream()`       | `AsyncGenerator[dict]`             | Streaming chat completion          |
| `models()`       | `list[dict]` (id, name, created)   | Available model list               |
| `health()`       | `dict` (status, message, model)    | Connectivity check                 |
| `provider_info()`| `dict`                              | Static metadata                    |
| `initialize()`   | `None`                             | Create SDK client, validate creds  |
| `cleanup()`      | `None`                             | Release resources                  |

### Response Format

All providers normalise responses to a common format:

```python
{
    "content": "Hello! How can I help?",
    "model": "gpt-4o",
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    "provider": "openai",
}
```

### Stream Format

Streaming yields dicts through an async generator:

```python
{"type": "chunk", "content": "Hello"}    # partial text
{"type": "done",  "content": "", "model": "gpt-4o"}  # finished
{"type": "error", "content": "..."}      # error occurred
```

The API layer wraps these in Server-Sent Events (SSE):

```
event: chunk
data: {"content": "Hello"}

event: done
data: {"provider": "openai", "model": "gpt-4o"}
```

## Registration Flow

1. On startup, `build_default_registries()` reads `Settings` and
   instantiates providers that have credentials configured.
2. Each provider calls `provider_registry.register(provider)`.
3. The `/health` endpoint reports which providers are registered
   and their live health status.
4. Application code calls `provider_registry.get("openai")` or
   `provider_registry.require("openai")` to obtain a provider.

```python
provider = provider_registry.require("openai")
result = await provider.generate(messages)
```

## Configuration

Providers are configured through environment variables:

| Variable              | Provider    | Required | Default                        |
|-----------------------|-------------|----------|--------------------------------|
| `OPENAI_API_KEY`      | OpenAI      | Yes      | —                              |
| `OPENAI_ORG_ID`       | OpenAI      | No       | —                              |
| `ANTHROPIC_API_KEY`   | Claude      | Yes      | —                              |
| `GEMINI_API_KEY`      | Gemini      | Yes      | —                              |
| `OLLAMA_BASE_URL`     | Ollama      | No       | `http://host.docker.internal:11434` |
| `OLLAMA_DEFAULT_MODEL`| Ollama      | No       | `llama3`                       |

Copy `.env.example` to `.env` and fill in the keys for the
providers you want to use.

## Adding a New Provider

1. Create `providers/new_provider.py` implementing `BaseProvider`.
2. Add the class to `providers/__init__.py`.
3. Add configuration fields to `configs/settings.py`.
4. Add registration logic in `backend/core/registries.py`.
5. Add the SDK package to `backend/requirements.txt`.

The new provider will be automatically discoverable through all
existing API endpoints and the UI.

## API Endpoints

| Method | Path                         | Description                         |
|--------|------------------------------|-------------------------------------|
| GET    | `/providers`                 | List registered providers           |
| GET    | `/providers/status`          | Live health for all providers       |
| GET    | `/providers/{name}/models`   | List models for a provider          |
| GET    | `/providers/{name}/health`   | Live health for a single provider   |
| POST   | `/chat`                      | Unified chat completion             |
| POST   | `/chat/stream`               | Streaming chat completion (SSE)     |

### Chat Request Format

```json
{
    "provider": "openai",
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}],
    "temperature": 0.7,
    "max_tokens": 1000,
    "stream": false
}
```

The same endpoint works for every provider. Just change the
`provider` and `model` fields.

## Provider Details

### OpenAI
- SDK: `openai` Python package
- Streaming: Yes, via `stream=True`
- Tool calling: Yes
- Models: Listed from `GET https://api.openai.com/v1/models`
- Default model: `gpt-4o`

### Anthropic Claude
- SDK: `anthropic` Python package
- Streaming: Yes, via `async with .messages.stream()`
- Tool calling: Yes (extended thinking)
- Models: Listed from Anthropic API
- Default model: `claude-3-5-sonnet-20241022`

### Google Gemini
- SDK: `google-genai` Python package
- Streaming: Yes, via `generate_content_stream()`
- Tool calling: Yes
- Models: Listed from Generative Language API
- Default model: `gemini-2.0-flash`

### Ollama (Local)
- SDK: `httpx` (direct REST API calls)
- Streaming: Yes, via NDJSON stream
- No API key required — ideal for air-gapped / on-premise
- Models: Listed from `GET /api/tags`
- Default model: `llama3`
- Default endpoint: `http://localhost:11434`
