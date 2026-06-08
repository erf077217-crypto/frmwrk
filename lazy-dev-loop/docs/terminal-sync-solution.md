# Terminal Synchronization Solution

## Problem

The previous architecture used `opencode serve` (headless HTTP API) with two
different client modes:

- **Extension prompts:** `opencode run --attach` — transient per-prompt HTTP
  client
- **Terminal:** `opencode attach --continue` — persistent TUI HTTP client

Both connected to the same serve process but maintained **separate session
state** at the bridge level. The bridge (`session_store.py`) tracked its own
conversation history, while OpenCode's serve process tracked its own internal
history. These diverged when the user interacted directly with the terminal.

## Solution: tmux-backed single-process architecture

### Architecture diagram

```
         ┌──────────────────────────────────────────────────┐
         │  Windows (bridge — FastAPI)                       │
         │                                                    │
         │  tmux_session.py  ─────►  wsl.exe bash bash        │
         │   │ send-keys              │                       │
         │   │ capture-pane           ▼                       │
         │   │                    tmux                        │
         │   │                  session                       │
         │   │              "lazy-dev-loop"                   │
         │   │                    │                            │
         │   │                    ▼                            │
         │   │              opencode (TUI)                     │
         │   │              ONE process                        │
         │   │              ONE session                        │
         │   │              ONE history                        │
         └───┼──────────────────────┬─────────────────────────┘
             │                      │
             ▼                      ▼
      ┌──────────────┐     ┌──────────────┐
      │  Extension    │     │  Terminal     │
      │  (send keys)  │     │  (tmux attach)│
      │  (read pane)  │     │  (full TUI)   │
      └──────────────┘     └──────────────┘
```

### Key changes

| Before | After |
|--------|-------|
| `opencode serve` (headless HTTP) | `opencode` (TUI mode) inside tmux |
| `opencode run --attach` for prompts | `tmux send-keys` for prompts |
| `opencode attach --continue` for terminal | `tmux attach` for terminal |
| Bridge stores duplicated history | Bridge reads history from tmux pane |
| `session_store.py` as primary history | tmux pane as primary, store as backup |

### How it works

1.  **Start:** Bridge creates a named tmux session (`lazy-dev-loop`) running
    `opencode` in the workspace directory inside WSL.

2.  **Prompt:** User types a prompt in the extension. Bridge sends it via
    `tmux send-keys -t lazy-dev-loop '<prompt>' Enter`. The text appears
    directly in the OpenCode TUI as if the user typed it.

3.  **Response:** Bridge polls `tmux capture-pane -t lazy-dev-loop -p` until
    the output stabilises (no change for 1.5 s). The new content is extracted
    by comparing before/after pane snapshots.

4.  **Terminal:** User clicks "Open Terminal" → a new console window runs
    `tmux attach -t lazy-dev-loop`. This attaches to the **exact same** tmux
    session, showing the same OpenCode process, same history, same state.

5.  **Shared state:** Everything — mode (`build`/`plan`), model, conversation
    history, agent state — is maintained by the single `opencode` process
    inside tmux. There is no duplication.

## Answers to explicit questions

### Can a tmux session become the authoritative session?

**YES.** The tmux session is the single source of truth. It owns the OpenCode
process. All state lives inside that process. The bridge and terminal are both
_clients_ of this session.

### Can extension commands be injected into the tmux session?

**YES.** `tmux send-keys -t lazy-dev-loop '<text>' Enter` injects text as if
typed directly into the terminal. The prompt appears in the OpenCode TUI, is
processed, and the response appears in the pane — visible to both the bridge
(via `capture-pane`) and any attached terminals.

### Can terminal activity be observed live?

**YES.** The bridge polls `tmux capture-pane` to read the current pane
content. Any output from OpenCode (responses, tool calls, errors) is visible.
The terminal attached via `tmux attach` sees everything in real time.

### Can both extension and terminal interact with the same session?

**YES.** Both send input to the same tmux session and read output from the
same pane. There is no split state.

### Do the extension and terminal share the same:
- **Process?** YES — one `opencode` process inside tmux.
- **Session state?** YES — OpenCode's internal session is the only session.
- **Model state?** YES — the single OpenCode process has one model config.
- **Conversation history?** YES — OpenCode's internal history is the only
  history. The bridge does not maintain a separate copy.

## Response detection

The `_wait_for_stable_output` method in `TmuxSession` handles response
detection:

1. Capture pane content before sending
2. Send prompt via `send-keys`
3. Poll `capture-pane` every 250 ms
4. When output has not changed for 1.5 seconds, consider the response complete
5. Extract the difference between before and after

This is reliable because:
- OpenCode's TUI shows a prompt line when ready for input (e.g., `> build ·
  big-pickle`)
- During processing, the TUI updates as tool calls and responses stream in
- The prompt line reappears when processing is complete

## tmux dependency

tmux must be installed inside WSL. The bridge auto-detects and offers to
install it:

```python
def _ensure_tmux() -> bool:
    if check_tmux():
        return True
    cmd = _wsl_cmd("sudo apt-get update -qq && sudo apt-get install -y -qq tmux")
    ...
```

If tmux cannot be installed, the session start returns a clear error message.

## Session persistence

`session_store.py` is retained as a **backup** persistence layer:

- When a prompt is sent, the bridge appends user + assistant messages to
  `sessions/{id}.json`
- Saved sessions appear in the extension UI for loading/archiving
- Loading a session stops the current tmux session and starts a fresh one
  (OpenCode's own session persistence is separate)

## UI simplification

The extension was simplified to a two-page layout:

**Page 1 — Session Management**
- New Session button
- Saved Sessions list (Load / Archive)
- Workspace selection
- Session status + Open Terminal

**Page 2 — Active Session**
- Prompt editor
- Response staging area
- Send to OpenCode
- Insert Into ChatGPT
- Open Terminal / Stop Session

The conversation timeline was removed entirely. History belongs in the
terminal. Users who want to review past interactions use the terminal's
scrollback.

## Validation

| Criterion | Status |
|-----------|--------|
| History not duplicated in extension | ✅ Timeline removed |
| History available in terminal scrollback | ✅ tmux scrollback |
| Session management UI exists | ✅ Page 1 |
| Save Session exists | ✅ Auto-saved on every prompt |
| Load Session exists | ✅ Saved Sessions list |
| New Session exists | ✅ New Session button |
| Shared source of truth | ✅ tmux session |
| Prompts from extension appear in terminal | ✅ tmux send-keys |
| Terminal activity visible to extension | ✅ tmux capture-pane |
| Model changes in terminal affect extension | ✅ Single process |
