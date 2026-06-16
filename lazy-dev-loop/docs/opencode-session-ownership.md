# Architecture Cleanup: OpenCode Session Ownership Audit

## Investigation Results

OpenCode has full native session management:

| Capability | Available | Command |
|---|---|---|
| List sessions | ✅ | `opencode session list` |
| Export session | ✅ | `opencode export <id>` (JSON with messages, tokens, workspace, model, agent) |
| Import session | ✅ | `opencode import <file>` |
| Continue last session | ✅ | `opencode --continue` |
| Continue specific session | ✅ | `opencode --session <id>` |
| Fork (copy) session | ✅ | `opencode --fork` |
| Delete session | ✅ | `opencode session delete <id>` |
| Auto-persist | ✅ | Built-in, stored at `~/.local/share/opencode/storage/` |

Session IDs follow the format `ses_[a-zA-Z0-9]+` and are created/managed entirely by OpenCode.

## Final Ownership Model

| Item | Owner | Mechanism |
|---|---|---|
| **Conversation history** | **OpenCode** | OpenCode tracks all messages internally. Export via `opencode export <id>` returns full message list with roles, timestamps, agent, model, diffs. |
| **Session persistence** | **OpenCode** | Sessions auto-saved to `~/.local/share/opencode/storage/`. No bridge-level persistence. `session_store.py` removed. |
| **Session restoration** | **OpenCode** | `opencode --session <id>` resumes any saved session in TUI mode. Terminal attached via `tmux attach` sees the exact restored state. |
| **Model state** | **OpenCode** | Model config is part of session metadata. Export includes `model.id` and `model.providerID`. Not tracked by bridge. |
| **Workspace state** | **OpenCode** | `info.directory` in export shows the workspace path. Bridge's `workspace_manager.py` sets the initial workspace; OpenCode consumes it. |

## Architecture Changes Made

### Removed
- `bridge/session_store.py` — bridge-level session persistence (replaced by OpenCode native)
- `bridge/tests/test_session_store.py` — 10 tests for removed module
- `bridge/sessions/` — 16 JSON files from old session store
- `POST /sessions/archive/{id}` endpoint
- `archiveSession()` JS function
- Bridge-generated UUID session IDs (`uuid.uuid4().hex[:12]`)
- `ss.append_message()` / `ss.finalize_session()` in removed `send_prompt()` / `stop()`
- `session_store` import from `tmux_session.py`

### Changed
- `bridge/tmux_session.py`:
  - `start()` accepts optional `session_id` for `opencode --session`
  - Removed session_store dependency
  - `send_prompt()` removed (replaced by `start_prompt_background` with `--session <id>`)
  - `stop()` no longer calls finalize
  - Added `list_sessions()` → delegates to `opencode session list`
  - Added `get_session(id)` → delegates to `opencode export <id>`
  - Added `_opencode_cli()` helper for opencode CLI calls
  - Added `_session_list()`, `_session_export()` parsers
- `bridge/main.py`:
  - `GET /sessions` → now calls `ocs.list_sessions()` (OpenCode CLI)
  - `GET /sessions/{id}` → now calls `ocs.get_session(id)` (OpenCode CLI)
  - `POST /sessions/load/{id}` → uses new `ocs.load_session()` with `--session`
  - `DELETE /sessions/{id}` added (replace for removed archive)
  - `POST /session/start` optionally accepts `session_id` query param
  - Removed archive endpoint
- `extension/sidepanel.js`:
  - `renderSavedSessions()` now uses OpenCode fields: title, session_id, updated
  - Removed `archiveSession()` function
  - Shows "from OpenCode" source in session list
  - Status panel shows "Source: opencode"
- `extension/sidepanel.html`: Added "Source" info row

### Kept
- `bridge/tmux_session.py` module-level functions (`start_session`, `stop_session`, etc.)
- `bridge/opencode_session.py` as thin re-export shim
- `POST /session/start`, `POST /session/stop`, `POST /session/prompt` — unchanged
- `GET /session/status`, `GET /session/preview` — unchanged
- `POST /terminal/open` — unchanged
- `POST /prompt` — legacy one-shot, kept
- `GET /health`, `GET /diagnostics` — unchanged
- Workspace management (`workspace_manager.py`) — kept but note: OpenCode also records workspace in session metadata

## Validation Steps

To validate the new architecture:

1. **Start bridge** — `uvicorn main:app --host 0.0.0.0 --port 7777`
2. **Set workspace** — `POST /workspace {"path": "C:\\path\\to\\repo"}`
3. **Start session** — `POST /session/start` → returns `{"success": true, "session_id": null}` (OpenCode generates ID internally)
4. **Send prompt** — `POST /session/prompt {"prompt": "hello"}` → returns response
5. **List sessions** — `GET /sessions` → returns OpenCode sessions with titles/updated
6. **Get session** — `GET /sessions/{id}` → returns full OpenCode export
7. **Open terminal** — `POST /terminal/open` → attaches to same tmux session
8. **Load session** — `POST /sessions/load/{id}` → stops current, starts `opencode --session <id>`
9. **Verify in terminal** — open terminal, see same conversation history
10. **Verify in extension** — session ID, title, workspace all match OpenCode data

## Key Principle

```
OpenCode
   ↓  owns session state, history, persistence, model, workspace
Bridge
   ↓  reflects state via OpenCode CLI, manages tmux + workspace setting
Extension
   ↓  displays state, sends prompts, shows response (no independent history)
```

The extension is a UI for OpenCode. It does not maintain its own session state, history, or metadata. All session data flows from OpenCode through the bridge to the extension.
