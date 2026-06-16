# Terminal Synchronization Investigation

## The Four Questions

### 1. Are the extension and terminal connected to the same process?

**YES.** Both the extension and the terminal connect to the same `opencode serve --port 14096` process running inside WSL.

- **Extension path:** `POST /session/prompt` → `opencode run --attach http://localhost:14096 <prompt>` (transient HTTP client)
- **Terminal path:** `POST /terminal/open` → `opencode attach --continue http://localhost:14096` (persistent TUI client)

Both use the same port (`SESSION_PORT = 14096`). The `wsl.exe` process tree is:

```
bridge/main.py (FastAPI, Windows Python)
  └── wsl.exe bash -ic "opencode serve --port 14096"     ← persistent process
        └── opencode serve (headless HTTP server)
              ├── wsl.exe bash -ic "opencode run --attach …"  ← per-prompt transient client
              └── wsl.exe bash -ic "opencode attach …"        ← terminal TUI client
```

**Evidence:** The `start()` method launches serve on port 14096. All subsequent prompts (via `start_prompt_background` with `--session`) and `open_terminal()` calls reference the same session.

### 2. Do the extension and terminal share the same session state?

**YES, at the OpenCode serve level.** The `opencode serve` process maintains a single session object in memory. Both `run --attach` and `attach --continue` interact with this same session.

**NO, at the bridge level.** The bridge (`opencode_session.py`) maintains its own `self.messages` list that is independent of OpenCode's internal session state. The bridge does not query OpenCode's serve instance for its session state; it only tracks what it sends/receives.

**Implication:** If a user changes mode in the terminal (e.g., `build` → `plan`), the next `run --attach` from the extension will use the new mode. But the bridge doesn't *know* the mode changed, and the extension UI has no way to display the current mode.

### 3. Do the extension and terminal share the same model state?

**YES.** The `opencode serve` process has one model configuration. All clients (extension, terminal) use the same model until the serve process is restarted. However, neither the bridge nor the extension UI exposes or displays the current model.

### 4. Do the extension and terminal share the same conversation history?

**PARTIALLY.** The `opencode serve` process tracks conversation history internally. Both `run --attach` and `attach --continue` see this history from the server's perspective. However:

- **Extension sees:** Only responses from `start_prompt_background` (JSON streaming). Full session history is available via `GET /sessions/{id}` which calls `opencode export`.
- **Terminal sees:** OpenCode's full internal session history, including any interactions made directly in the TUI.

**Gap:** If a user interacts with OpenCode directly in the terminal TUI, those interactions are NOT reflected in the extension's conversation timeline. The bridge has no way to poll the serve instance for new messages.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         Bridge (source of truth for extension)    │
│  session_store.py ──► sessions/{id}.json                          │
│       ▲                                                           │
│       │ reads/writes                                              │
│  opencode_session.py                                              │
│  ┌─────────────────────────────────────┐                          │
│  │ self.messages = [                   │                          │
│  │   {role:"user", content:"..."},     │                          │
│  │   {role:"assistant", content:"..."},│                          │
│  │ ]                                   │                          │
│  └──────────┬──────────────────────────┘                          │
│             │                                                     │
│             ▼                                                     │
│  ┌─────────────────────┐    ┌──────────────────────────┐          │
│  │ opencode run --attach│    │ opencode attach --continue│         │
│  │ (transient, per-prompt)   │ (persistent TUI)         │         │
│  └──────────┬──────────┘    └───────────┬──────────────┘          │
│             │                           │                          │
└─────────────┼───────────────────────────┼──────────────────────────┘
              │                           │
              ▼                           ▼
     ┌──────────────────────────────────────────┐
     │       opencode serve --port 14096         │
     │  (headless HTTP server, one session)      │
     │  ┌────────────────────────────────────┐   │
     │  │ internal session state:            │   │
     │  │ - conversation history             │   │
     │  │ - mode (build/plan)                │   │
     │  │ - model config                     │   │
     │  │ - agent state                      │   │
     │  └────────────────────────────────────┘   │
     └──────────────────────────────────────────┘
```

## Can perfect synchronization be achieved?

### With the current architecture: **NO**

The fundamental limitation is that the bridge and OpenCode serve instance maintain **separate** session state. The bridge records what it sends/receives, while OpenCode records everything internally. There is no API for the bridge to:

1. Query OpenCode's current mode (`build` vs `plan`)
2. Poll for new messages added by the TUI
3. Subscribe to state change events from serve

### Possible solutions

| Solution | Effort | Synchronization | Notes |
|----------|--------|-----------------|-------|
| **A. Bridge as sole client (current + polling)** | Low | Partial | Bridge stores history. Terminal is independent. Extension polls `GET /session/messages`. User must use extension for prompts visible in timeline. |
| **B. tmux-backed session** | High | Full | Run `opencode` (not `serve`) inside tmux. Bridge writes prompts to tmux stdin, reads responses from tmux buffer. Terminal attaches to same tmux session. Everything shares one process, one PTY, one state. |
| **C. OpenCode session export API** | Medium | After-the-fact | After each interaction (or on demand), call `opencode export <sessionId>` to pull full history from serve into the bridge. Requires session ID tracking. |
| **D. Route all prompts through serve, bridge polls serve state** | Medium | Near-full | Use `opencode run --attach` for prompts (current). Bridge periodically calls `opencode session list` or serves's internal API to sync state. |

### Recommendation

For this phase, **Option A (current approach)** is the right choice:

1. The bridge is the **source of truth for the extension's UI**
2. Session history is persisted in `sessions/{id}.json` via `session_store.py`
3. The conversation timeline is populated from bridge-tracked messages
4. Terminal shows OpenCode's internal session (via `opencode attach --continue`)

**For future phases**, implement **Option B (tmux)** if true shared state is required. The tmux approach would:

1. Start `opencode` (TUI mode, not `serve`) inside a named tmux session
2. Bridge sends prompts via `tmux send-keys -t opencode 'prompt' Enter`
3. Bridge reads responses via `tmux capture-pane -t opencode -p`
4. Terminal opens via `tmux attach -t opencode`
5. All interactions share one PTY, one process, one state

The downside of tmux: more complex process management, tmux dependency on WSL, and harder error handling.

## Auto-open terminal recommendation

**Do not auto-open terminal.** The "Open Terminal" button intentionally gives the user control over when they want the TUI. Auto-opening would:

- Launch a console window the user might not want
- Consume system resources unnecessarily
- Not improve synchronization (terminal is still a separate HTTP client to serve)

If auto-open were implemented, it would simplify nothing — the terminal and extension would still be independent HTTP clients to the same serve process. The synchronization gap exists at the architectural level, not the timing level.
