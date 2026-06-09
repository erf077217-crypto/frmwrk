# Backend

FastAPI application that serves as the platform's control plane.

Provides REST endpoints for managing providers, agents, tools, and
system health. Uses dependency injection to wire together the
provider, agent, and tool subsystems.

- `api/` — Route handlers (health, providers, agents, tools)
- `core/` — Core domain logic (registration, orchestration)
- `models/` — Pydantic schemas for request/response contracts
