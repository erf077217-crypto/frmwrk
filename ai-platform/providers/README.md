# Providers

LLM provider abstraction layer.

Every provider implements the same `BaseProvider` interface so the
platform can swap models without changing calling code.

- `base.py` — Abstract interface
- `openai_provider.py` — Skeleton
- `claude_provider.py` — Skeleton
- `gemini_provider.py` — Skeleton
- `ollama_provider.py` — Skeleton
