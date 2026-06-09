# AI Platform

Enterprise internal AI platform for orchestrating coding agents,
documentation agents, testing agents, RAG workflows, and multi-LLM
provider integrations.

## Architecture

```
ai-platform/
├── backend/      # FastAPI application server
├── frontend/     # Web-based management UI
├── agents/       # Agent runtime and definitions
├── providers/    # LLM provider abstractions
├── tools/        # Tool framework and built-in tools
├── workflows/    # Workflow orchestration (future)
├── knowledge/    # Knowledge base / RAG (future)
├── security/     # Auth, approval workflows (future)
├── configs/      # Configuration management
├── tests/        # Unit and integration tests
└── docs/         # Architecture and user documentation
```

## Quick Start

```bash
# Backend
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## Status

Phase 1: Foundation complete. No AI workflows implemented yet.
