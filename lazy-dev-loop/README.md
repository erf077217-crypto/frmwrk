# Lazy Developer Loop

A Chrome extension and local bridge service that sends prompts from ChatGPT to OpenCode and returns the response.

## Architecture

```
Windows
┌──────────────────────────────────────────────────────────┐
│  Chrome Side Panel                                       │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────┐   │
│  │ Prompt + Response │  │ Saved        │  │ Session  │   │
│  │ (ANSI-stripped)   │  │ Sessions     │  │ Status   │   │
│  │ Insert to ChatGPT │  │ (Load/       │  │ (tmux)  │   │
│  └────────┬─────────┘  │ Archive)     │  │ Start/   │   │
│           │  HTTP POST │              │  │ Stop     │   │
│           ▼  /session/ │  Workspace   │  │ Open     │   │
│           │   prompt   │  Selector    │  │ Terminal │   │
│           ▼            └──────────────┘  └──────────┘   │
│   FastAPI Bridge (Windows Python)                         │
│   tmux_session.py   workspace_manager.py                  │
│   session_store.py                                        │
│         │                                                  │
│    tmux send-keys / tmux capture-pane / tmux attach       │
│    via: wsl.exe bash -ic "tmux <cmd>"                    │
└────────────────────┬─────────────────────────────────────┘
                      │
               WSL ───┘
┌──────────────────────────────────────────────────────────┐
│  wsl.exe bash -c "tmux new-session -s lazy-dev-loop"    │
│    └── runs opencode (TUI, not serve) inside tmux pane   │
│                                                           │
│  tmux send-keys -t lazy-dev-loop '<prompt>' Enter        │
│    └── injects prompt directly into the single process   │
│                                                           │
│  tmux capture-pane -t lazy-dev-loop -p                   │
│    └── reads pane output (polled for stable response)    │
│                                                           │
│  tmux attach -t lazy-dev-loop                            │
│    └── terminal attaches to EXACT same tmux session      │
└──────────────────────────────────────────────────────────┘
```

## Project Structure

```
lazy-dev-loop/
├── extension/              # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── background.js
│   ├── content_script.js
│   ├── sidepanel.html      # Main UI (workspace, session, prompt, response)
│   ├── sidepanel.js
│   ├── popup.html          # Minimal popup (legacy)
│   ├── popup.js
│   └── vendor/             # Bundled dependencies
│       ├── xterm.min.js
│       └── xterm.min.css
├── bridge/                 # Python FastAPI bridge service
│   ├── main.py
│   ├── config.py
│   ├── opencode_runner.py  # One-shot subprocess runner (/prompt, /health, /diagnostics)
│   ├── tmux_session.py     # Tmux-backed session manager (authoritative)
│   ├── opencode_session.py # Thin re-export shim for tmux_session (backward compat)
│   ├── session_store.py    # Session persistence to disk (backup)
│   ├── workspace_manager.py# Workspace management (Windows→WSL path conversion)
│   ├── workspace.json      # Persisted active workspace path
│   ├── run.sh              # Startup script (Git Bash / WSL)
│   ├── run.bat             # Startup script (Windows cmd)
│   └── requirements.txt
├── docs/
└── README.md
```

## Requirements

- **Windows 10/11** with WSL installed
- **Python 3.10+** (Windows)
- **OpenCode CLI** installed inside WSL
- **Node.js** (inside WSL, required by OpenCode)

## Installation

### 1. WSL + OpenCode Setup

Check that WSL is available:

```bash
wsl --status
```

If not installed:

```bash
wsl --install
```

Inside your WSL distribution, install OpenCode:

```bash
# Install Node.js (if not already installed)
sudo apt update && sudo apt install -y nodejs npm

# Install OpenCode
npm install -g @opencode/cli
```

Verify OpenCode is accessible from WSL:

```bash
wsl bash -lc "opencode --help"
```

### 2. Bridge Service

```bash
cd lazy-dev-loop/bridge
pip install -r requirements.txt
```

### 3. Chrome Extension

1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked**
4. Select the `lazy-dev-loop/extension` folder
5. The extension is now installed

## Configuration

Edit `bridge/config.py` to customise behaviour:

```python
WSL_DISTRO = None              # Set to "Ubuntu" or "Debian" for a specific distro
OPENCODE_COMMAND = "opencode"  # The opencode binary name/path inside WSL
RUN_TIMEOUT = 120              # Maximum seconds to wait for OpenCode prompt response
USE_INTERACTIVE_SHELL = True   # Use -ic (interactive) instead of -lc (login)
```

- **WSL_DISTRO** — leave as `None` to use the default WSL distro; set to a distro name (e.g. `"Ubuntu"`) if you have multiple distros.
- **USE_INTERACTIVE_SHELL** — when `True`, commands run via `bash -ic` (interactive). When `False`, uses `bash -lc` (login). Interactive mode loads `~/.bashrc`, which is typically where `npm` global bins are added to PATH.

Workspace is set at runtime via the API or side panel UI. Persisted in `bridge/workspace.json`.

## Running

### Start the Bridge Service

**Recommended — one-command startup:**

```bash
# Git Bash / WSL
cd lazy-dev-loop/bridge
./run.sh

# Windows cmd
run.bat
```

The script auto-detects the venv's uvicorn and starts on port 7777.

**Manual start (alternative):**

```bash
cd lazy-dev-loop/bridge
uvicorn main:app --host 0.0.0.0 --port 7777
```

The server starts at `http://localhost:7777`.

### Health Check

```bash
curl http://localhost:7777/health
```

Expected response when everything is working:

```json
{"status":"ok","wsl_available":true,"opencode_available":true}
```

### Diagnostics

If `opencode_available` is `false`, run the diagnostics endpoint to investigate:

```bash
curl http://localhost:7777/diagnostics | python3 -m json.tool
```

Returns structured info including:

- `whoami` — the Linux user running the commands
- `path` — the effective PATH inside the WSL shell
- `command_v`, `which_opencode`, `type_opencode` — results of each discovery command
- `shell_mode_comparison` — compares `bash -lc` vs `bash -ic` for `command -v`, `which`, and `whoami`
- `user_mismatch` — checks whether the user differs between shell modes
- `discovered_opencode_path` — the final resolved path from the fallback chain

### Session API (persistent sessions)

**1. Set a workspace** (required before starting a session):

```bash
curl -X POST http://localhost:7777/workspace \
  -H "Content-Type: application/json" \
  -d '{"path": "C:\\Users\\you\\Projects\\my-repo"}'
```

Returns the WSL-converted path.

**2. Start a persistent session:**

```bash
curl -X POST http://localhost:7777/session/start
```

Launches `opencode serve --port 14096` in the workspace. Returns `session_id`, `pid`, `port`.

**3. Check session status:**

```bash
curl http://localhost:7777/session/status
```

Returns: `active`, `session_id`, `pid`, `uptime`, `port`, `workspace`.

**4. Send prompts to the active session:**

```bash
curl -X POST http://localhost:7777/session/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain this codebase"}'
```

Sends the prompt to the running `opencode serve` instance via `run --attach`. Returns the response.

**5. Open a real OS terminal:**

```bash
curl -X POST http://localhost:7777/terminal/open
```

Opens a new WSL terminal window running `opencode attach http://localhost:14096`, connected to the active session.

**6. Stop the session:**

```bash
curl -X POST http://localhost:7777/session/stop
```

Terminates the `opencode serve` process.

### Legacy Prompt Endpoint (still available)

```bash
curl -X POST http://localhost:7777/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "hello"}'
```

```json
{"response":"...OpenCode output...","success":true}
```

## How It Works

### Prompt → Bridge → OpenCode (Legacy)

1. The Chrome extension sends highlighted text as `POST /prompt`
2. The FastAPI bridge calls `opencode_runner.run_opencode()`
3. Builds the command `wsl.exe bash -ic "opencode run '<prompt>'"` and runs it via `subprocess.run()`
4. Returns output, then OpenCode exits. Session state is lost.

### Persistent Session API (current)

The architecture uses `opencode serve` as a long-lived background server and `opencode run --attach` as a transient client:

1. **`POST /workspace`** — sets the workspace directory. The bridge validates the path (converts Windows `C:\...` to WSL `/mnt/c/...`) and verifies it exists inside WSL.

2. **`POST /session/start`** — launches `wsl.exe bash -ic "opencode serve --port 14096"` inside the workspace directory. This keeps running as a foreground process, maintaining:
   - Repository context (git history, file tree)
   - Session state (conversation history)
   - Agent state (tools, permissions, decisions)
   - Command history

3. **`POST /session/prompt`** — runs `wsl.exe bash -ic "opencode run --attach http://localhost:14096 '<prompt>'"`. This lightweight CLI client:
   - Connects to the running `serve` instance
   - Sends the prompt
   - Waits for the response
   - Outputs it to stdout (with ANSI codes)
   - Exits
   
   The `serve` server persists the session between prompts.

4. **`POST /terminal/open`** — opens a new OS console window running `wsl.exe bash -ic "opencode attach http://localhost:14096"`. This provides:
   - Full interactive TUI connected to the same session
   - Real terminal rendering (no browser emulation)
   - Direct access to OpenCode's interactive interface

5. **`POST /session/stop`** — terminates the `opencode serve` process (SIGTERM → 5s → SIGKILL). The session is lost after stop.

### Legacy endpoints (backward compat)

All previous endpoints (`/session/stream`, `/ws/session/`, `/session/output`) are available under `/legacy/` prefix for backward compatibility.

### Side Panel (primary UI)

The Chrome Side Panel (`sidepanel.html`) is the main user interface:

1. **Prompt section** — type or paste a prompt, press Enter or click **Send to OpenCode**. The prompt is sent to the persistent OpenCode session via `POST /session/prompt`.
2. **Response section** — displays the clean (ANSI-stripped) response from OpenCode. **Insert Into ChatGPT** sends selected text to the active ChatGPT tab.
3. **Workspace section** — shows the current workspace path. Click **Change Workspace** to set a new working directory. Path is validated against WSL.
4. **Session section** — shows session state (Active/Inactive), Session ID, PID, port, and uptime. **Start Session** launches `opencode serve`. **Stop Session** terminates it.
5. **Terminal section** — **Open Terminal** launches a real OS terminal window (via WSL) running `opencode attach` connected to the active session.
6. **Diagnostics** — collapsible section with Ping ChatGPT, Tab Info, and Refresh Status buttons.

Session status is polled every 5 seconds and displayed in the sidebar.

When text is highlighted and the context menu **Send To OpenCode** is used:
1. Background opens the side panel and stores the prompt
2. The side panel displays the prompt and sends it via `POST /session/prompt`
3. The response appears in the Response section

### Insert Response Into ChatGPT

1. The side panel (or popup) displays the response text
2. **Select part of the text** (or leave all selected by default)
3. Click **Insert Into ChatGPT**
4. The background script finds the active ChatGPT tab and forwards the text to the content script
5. The content script (`content_script.js`) locates the ChatGPT prompt `<div contenteditable>` and inserts the text at the current cursor position
6. Existing text in the textbox is preserved
7. A success or error message is shown

## Permissions Used

| Permission | Purpose |
|---|---|
| `contextMenus` | Add "Send To OpenCode" right-click menu |
| `storage` | Store session IDs and responses between UI opens |
| `activeTab` | Access the currently focused ChatGPT tab to insert text |
| `scripting` | Programmatically inject content script if not already loaded |
| `sidePanel` | Open the Chrome Side Panel as the primary UI |
| `http://localhost:7777/*` | Send requests to the local bridge |
| `https://chatgpt.com/*` | Content script runs on ChatGPT to enable text insertion |

## Timeout Behaviour

- The default timeout is **120 seconds**
- Configurable in `config.py` via `RUN_TIMEOUT`
- Timeouts return `{"response": "OpenCode timed out after 120 seconds.", "success": false}`

## Testing the Full Workflow

### Side Panel (recommended)

1. Ensure WSL is installed (`wsl --status`)
2. Ensure OpenCode is installed inside WSL (`wsl bash -lc "opencode --help"`)
3. Start the bridge service: `cd lazy-dev-loop/bridge && ./run.sh`
4. Verify health: `curl http://localhost:7777/health`
5. Open Chrome → `chrome://extensions` → Load unpacked → select `lazy-dev-loop/extension`
6. **Click the extension icon** in the toolbar to open the side panel
7. In the side panel, type a prompt and click **Send to OpenCode**
8. Watch live console output appear in the **OpenCode Console** section
9. When finished, the **Response** section shows the full output
10. Open a ChatGPT conversation in another tab
11. In the side panel response, select text (or leave unselected) and click **Insert Into ChatGPT**
12. The text appears in the ChatGPT textbox at the cursor position
13. Review and manually send the message

### Context Menu (quick access)

1. On any web page, **highlight text** with your cursor
2. **Right-click** the highlighted text
3. Select **Send To OpenCode** from the context menu
4. The side panel opens and streams the OpenCode session live
5. Use the side panel to view the response and insert into ChatGPT

### Insertion scenarios

| Action | Result |
|---|---|
| Select text → Insert | Only selected text goes into ChatGPT |
| No selection → Insert | Entire response goes into ChatGPT |
| Existing text in textbox | Existing text preserved, inserted text appended at cursor |
| After insertion | Message is NOT sent automatically |

### Live terminal verification

Run a prompt and check that the **Terminal** section shows output as it arrives, with full ANSI color rendering and cursor handling. The raw output goes through an xterm.js terminal emulator via WebSocket, while the **Response** section shows a clean ANSI-stripped version.

## Troubleshooting

| Problem | Likely Cause | Solution |
|---|---|---|
| `wsl.exe not found` | WSL not installed | Run `wsl --install` as admin |
| `wsl_available: false` | WSL not running or missing | Run `wsl --status` to check |
| `opencode_available: false` | OpenCode not found by shell | See WSL PATH section below |
| `"Connection refused"` | Bridge not running | Start `uvicorn main:app` on port 7777 |
| `"Timed out"` | Prompt took >120s | Increase `RUN_TIMEOUT` in `config.py` |
| Extension doesn't show context menu | Extension not reloaded | Go to `chrome://extensions` and reload |
| Insert button says "No ChatGPT tab found" | ChatGPT not open | Open `https://chatgpt.com` in any tab |
| Insert button says "ChatGPT textbox not found" | Page not fully loaded | Refresh ChatGPT page and try again |
| Insert button says "Failed to reach ChatGPT page" | Content script not injected | Reload extension at `chrome://extensions` |
| Text not appearing in ChatGPT textbox | Focus on wrong element | Click inside the ChatGPT textbox first, then Insert |
| Side panel not opening | Permission not granted | Go to `chrome://extensions` → extension → "Inspect views" and check for errors |
| Terminal shows "(connecting…)" forever | Bridge not running | Start the bridge with `./run.sh` |
| WebSocket connection refused | `websockets` package not installed | Run `pip install websockets` |
| ANSI codes visible as literal text instead of colors | xterm.js not loaded | Check CSP in manifest.json allows `https://cdn.jsdelivr.net` |
| Terminal stays black after session starts | OpenCode producing buffered output with no PTY | The `script -qfc` wrapper ensures a PTY is created inside WSL |
| Both terminal and response are empty | OpenCode not found | Run diagnostics: `curl http://localhost:7777/diagnostics` |
| `./run.sh: uvicorn not found` | Venv not detected | Activate venv manually: `source ../../.venv/Scripts/activate` then `uvicorn main:app` |
| Quote or escaping errors in prompt | Complex characters | The runner uses `shlex.quote()` for bash-safe escaping |
| `wsl: Bad address` or distro errors | Wrong `WSL_DISTRO` | Check your distro name with `wsl -l -v` |

### WSL PATH and Shell Detection Issues

The most common issue is that `opencode` works inside a WSL terminal but the bridge reports `opencode_available: false`.

**Root cause:** OpenCode is typically installed globally via npm, which places the binary in a directory like:

| npm prefix | Typical binary path |
|---|---|
| default (nvm-managed) | `~/.nvm/versions/node/vX.Y.Z/bin/opencode` |
| system npm | `/usr/local/bin/opencode` |
| default (non-nvm) | `~/.npm-global/bin/opencode` (or `/home/user/.npm/bin/opencode`) |
| nvm default alias | `~/.nvm/versions/node/default/bin/opencode` |

These directories are added to PATH inside `~/.bashrc`, but **not** in `~/.profile` or `~/.bash_profile`. Since `bash -lc` (login shell) reads `~/.profile` / `~/.bash_profile` — not `~/.bashrc` — non-interactive shells launched by the bridge may have a different PATH.

#### Shell mode comparison

| Mode | Flag | Reads | PATH contents |
|---|---|---|---|
| Interactive | `bash -ic` | `.bashrc` | Includes npm bin dirs, nvm shims |
| Login (non-interactive) | `bash -lc` | `.profile`, `.bash_profile` | Basic system PATH, may miss npm bins |
| Interactive + Login | `bash -lic` | Both `.bashrc` and `.profile` | Full user PATH |

**Default fix:** The bridge uses `USE_INTERACTIVE_SHELL = True` which runs commands with `bash -ic`, loading `~/.bashrc`. This is sufficient for most WSL+npm setups.

#### If OpenCode remains undetected

1. Run the diagnostics endpoint to compare shell modes:

   ```bash
   curl http://localhost:7777/diagnostics | python3 -m json.tool
   ```

   Check `shell_mode_comparison` to see if `-ic` mode finds opencode but `-lc` does not.

2. Find where opencode lives inside WSL:

   ```bash
   wsl bash -ic "which opencode"
   ```

3. Add the directory to `~/.profile` so it works in both modes:

   ```bash
   wsl bash -lc 'echo "export PATH=\"\$HOME/.npm-global/bin:\$PATH\"" >> ~/.profile'
   ```

   Adjust the path to match the one from `which opencode`.

#### Useful diagnostic commands

```bash
# Check WSL status
wsl --status

# List installed distros
wsl -l -v

# Compare PATH in interactive vs login shells
wsl bash -lc "echo \$PATH" | tr ':' '\n'
wsl bash -ic "echo \$PATH" | tr ':' '\n'

# Find opencode in interactive shell
wsl bash -ic "which opencode"

# Check npm global prefix
wsl bash -ic "npm prefix -g"

# Run OpenCode from Windows via WSL
wsl bash -ic "opencode run 'Explain this codebase'"
```

## Development Status

### Phase 1.0 — Persistent Sessions, Workspace Management & Real Terminal ✅

- [x] Workspace management (`POST /workspace`, `GET /workspace`) with Windows↔WSL path conversion
- [x] `workspace_manager.py` — path validation, `workspace.json` persistence
- [x] Persistent OpenCode session via `opencode serve --port <port>` (long-lived engine)
- [x] `opencode_session.py` — `start()`, `stop()`, `status()`, `open_terminal()`
- [x] `POST /session/start` — launches `opencode serve` in workspace
- [x] `POST /session/prompt` — sends prompt via `opencode run --attach`
- [x] `GET /session/status` — returns active state, PID, uptime, port, session_id, workspace
- [x] `POST /terminal/open` — launches new WSL console with `opencode attach`
- [x] `POST /session/stop` — terminates the serve process
- [x] Legacy endpoints moved under `/legacy/*` for backward compatibility
- [x] Side panel rewritten: workspace panel, session panel, Open Terminal button
- [x] Periodic status polling (5s) in side panel
- [x] `--format json` support for machine-readable prompt output
- [x] Python `subprocess.CREATE_NEW_CONSOLE` (value 16) for terminal launch on Windows

### Phase 0.5 — PTY Terminal, WebSocket & xterm.js (replaced by Phase 1.0) ⏪

- [x] FastAPI server with `POST /prompt` endpoint (now legacy)
- [x] Chrome extension with context menu
- [x] E2E flow: selected text → context menu → bridge → response in side panel
- [x] WSL-based OpenCode execution via `wsl.exe bash -ic`
- [x] Configurable WSL distro, command, timeout, and shell mode
- [x] `GET /health` endpoint for WSL + OpenCode validation
- [x] Safe prompt escaping via `shlex.quote()`
- [x] Graceful error messages (HTTP 200 with `success: false`)
- [x] Robust OpenCode discovery with 3-tier fallback
- [x] Legacy session API moved to `/legacy/session/*`
- [x] Insert Into ChatGPT (preserves existing text, no auto-send)
- [x] ANSI escape sequence stripping for clean output display
- [x] xterm.js terminal (removed — replaced with real OS terminal)
- [x] WebSocket streaming (removed — replaced with HTTP prompt/attach)
- [x] PTY via `script -qfc` (removed — no longer needed)
