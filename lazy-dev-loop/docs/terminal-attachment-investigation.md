# Terminal Attachment Investigation

## The Four Questions

### 1. Is the terminal connected to the active OpenCode process?

**YES.** The `open_terminal()` call in `opencode_session.py:150-174` runs:

```
opencode attach --continue http://localhost:14096
```

This connects to the same `opencode serve --port 14096` instance that was launched by `start()`. The port is hardcoded at `SESSION_PORT = 14096`, so both `serve` and `attach` point at the same HTTP server.

### 2. Is the terminal attached to the active PTY?

**NO.** There is no shared PTY in the current architecture:

- `opencode serve` is a **headless HTTP server**. It does not create a PTY.
- `opencode run --attach http://localhost:port <prompt>` spawns a **transient** subprocess each time. It connects to the serve instance via HTTP, sends a prompt, receives the response, and exits. No PTY is created.
- `opencode attach --continue http://localhost:port` opens a TUI that connects to the same serve instance via HTTP. The TUI renders its own terminal UI, but it's a **client**, not a PTY attachment to a running process.

The serve instance maintains session state in memory (conversation history, agent state, file context), but there is no shared terminal multiplexer (tmux, screen, PTY) that both the `run --attach` clients and the `attach` TUI share.

### 3. Is a new process being launched?

**YES.** `open_terminal()` calls `subprocess.Popen(cmd, creationflags=CREATE_NEW_CONSOLE)` which launches a brand‑new `wsl.exe bash -ic "opencode attach …"` process in a separate Windows console window. This is a fresh OS process; it is not forking or attaching to the existing `opencode serve` process.

### 4. Is the session history accessible?

**YES, with `--continue`.** OpenCode's `attach` command accepts a `--continue` (`-c`) flag that tells the server to resume the **last** session. The fix applied in this phase adds `--continue` to the attach command, so the TUI now shows the existing session instead of starting a blank one.

However, the `run --attach` prompts are sent as **separate HTTP requests** to the serve instance. Whether those individual prompts and responses appear in the `attach` TUI's scrollback depends on:

- The session object on the serve side — OpenCode does track conversation history per session.
- The TUI rendering — the `attach` TUI requests the current state from serve, which should include previous messages.

## Root cause of the "fresh start" behavior

Before the fix, `open_terminal()` ran:

```
opencode attach http://localhost:14096
```

Without `--continue`, OpenCode's `attach` command **starts a new session** instead of resuming the existing one. The serve instance may still have the old session in memory, but the attach client does not request it.

## Fix applied

Added `--continue` flag to the attach command in `opencode_session.py:158`:

```python
# Before
inner = f"{config.OPENCODE_COMMAND} attach http://localhost:{port}"

# After
inner = f"{config.OPENCODE_COMMAND} attach --continue http://localhost:{port}"
```

With `--continue`, the TUI tells the server "give me the last active session," and the server responds with the conversation history, tool call state, and agent context from the persistent session.

## Attachment strategies evaluated

| Strategy | Feasibility | Notes |
|----------|-------------|-------|
| PTY attachment | Not possible | `opencode serve` is HTTP‑based, not PTY‑based |
| tmux/screen | Possible but fragile | Would need to wrap `serve` in tmux, then `attach` via `tmux attach`. Adds tmux dependency on WSL. No benefit over `--continue`. |
| `opencode attach --continue` | ✅ Implemented | Native OpenCode feature. Lightest approach. |
| `opencode attach --session <id>` | Available as fallback | Requires tracking session IDs from serve output. `--continue` is simpler for the single‑session case. |
| Shared PTY (Phase 0.5 revert) | Not recommended | Would revert to the old `script -qfc` / WebSocket / xterm.js design, which was explicitly replaced. |

## User experience after fix

1. User starts a session (**Start Session** → `opencode serve --port 14096`)
2. User sends prompts through the extension (**Send to OpenCode** → `opencode run --attach …`)
3. OpenCode continues running (serve process persists)
4. User clicks **Open Terminal**
5. Terminal opens showing the **existing session** with:
   - Previous prompts and responses
   - Agent activity and tool calls
   - Repository actions
   - Full conversation history

6. User can continue interacting with OpenCode directly in the TUI

## If `--continue` is insufficient

If the TUI still appears disconnected from the history of `run --attach` prompts:

**Alternative 1 — Track and pass session ID:**
After `start()` launches `serve`, poll its output or use `opencode session list` to discover the active session ID. Pass `--session <id>` explicitly in the attach command.

**Alternative 2 — Use `opencode export <id>` for programmatic history retrieval:**
The bridge can call `opencode export <sessionID>` to fetch full session history as JSON, exposing it in the side panel response area.

**Alternative 3 — Route all prompts through a persistent tmux session:**
Instead of `opencode run --attach`, write prompts to a tmux session running the OpenCode TUI, and read responses by capturing tmux buffer output. This gives true shared terminal access but is significantly more complex.
