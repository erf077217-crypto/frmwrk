const BRIDGE = (() => {
  try {
    const stored = localStorage.getItem("BRIDGE_URL");
    if (stored) return stored;
  } catch {}
  return "http://localhost:7777";
})();

// ── DOM refs ──────────────────────────────────────────────────────────────

const statusBar          = document.getElementById("statusBar");
const debugLog           = document.getElementById("debugLog");

// Workspace
const workspacePath      = document.getElementById("workspacePath");
const workspaceChangeBtn = document.getElementById("workspaceChangeBtn");
const workspaceEditRow   = document.getElementById("workspaceEditRow");
const workspaceInput     = document.getElementById("workspaceInput");
const workspaceSetBtn    = document.getElementById("workspaceSetBtn");
const workspaceCancelBtn = document.getElementById("workspaceCancelBtn");

// Session controls
const newSessionBtn      = document.getElementById("newSessionBtn");
const stopSessionBtn     = document.getElementById("stopSessionBtn");
const sessionStateBadge  = document.getElementById("sessionStateBadge");
const sessionIdDisplay   = document.getElementById("sessionIdDisplay");
const sessionUptimeDisplay = document.getElementById("sessionUptimeDisplay");

// Prompt
const promptInput        = document.getElementById("promptInput");
const sendBtn            = document.getElementById("sendBtn");
const modeToggleBtn      = document.getElementById("modeToggleBtn");
let currentMode          = "summary";

// Response
const responseViewer     = document.getElementById("responseViewer");
const fetchBtn           = document.getElementById("fetchBtn");
const insertBtn          = document.getElementById("insertBtn");

// Terminal
const openTerminalBtn    = document.getElementById("openTerminalBtn");

// Diagnostics
const pingBtn            = document.getElementById("pingBtn");
const tabInfoBtn         = document.getElementById("tabInfoBtn");
const refreshBtn         = document.getElementById("refreshBtn");

// Debug
const debugCheckbox      = document.getElementById("debugCheckbox");

// ── State ─────────────────────────────────────────────────────────────────

let statusPollInterval = null;

// ── Debug logging ─────────────────────────────────────────────────────────

const MAX_LOG_ENTRIES = 1000;
let debugLogBuffer = [];
let debugEnabled = false;

function debug(msg) {
  const entry = `[${new Date().toLocaleTimeString()}] ${msg}`;
  debugLogBuffer.push(entry);
  if (debugLogBuffer.length > MAX_LOG_ENTRIES) {
    debugLogBuffer.shift();
  }
  if (debugEnabled) {
    debugLog.classList.remove("hidden");
    debugLog.textContent = debugLogBuffer.join("\n");
    debugLog.scrollTop = debugLog.scrollHeight;
  }
}

function setDebugUI(enabled) {
  debugEnabled = enabled;
  debugCheckbox.checked = enabled;
  if (!enabled) {
    debugLog.textContent = "";
    debugLog.classList.add("hidden");
  } else if (debugLogBuffer.length > 0) {
    debugLog.classList.remove("hidden");
    debugLog.textContent = debugLogBuffer.join("\n");
    debugLog.scrollTop = debugLog.scrollHeight;
  }
}

async function fetchDebugStatus() {
  try {
    const r = await fetch(`${BRIDGE}/debug/status`);
    const data = await r.json();
    setDebugUI(data.enabled === true);
  } catch (err) {
    // bridge not reachable — keep current state
  }
}

async function toggleDebug(enabled) {
  try {
    const endpoint = enabled ? "enable" : "disable";
    await fetch(`${BRIDGE}/debug/${endpoint}`, { method: "POST" });
    setDebugUI(enabled);
    if (enabled) debug("Debug logging enabled");
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

debugCheckbox.addEventListener("change", () => {
  toggleDebug(debugCheckbox.checked);
});

// ── Helpers ──────────────────────────────────────────────────────────────

function setStatus(msg, cls) {
  statusBar.textContent = msg;
  statusBar.className = cls || "status-info";
}

function debug(msg) {
  debugLog.classList.remove("hidden");
  debugLog.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
  debugLog.scrollTop = debugLog.scrollHeight;
}

// ── Render ────────────────────────────────────────────────────────────────

function render(data) {
  if (!data) return;
  const active = data.active;
  const sid = data.session_id || "—";
  const uptime = data.uptime;

  sessionStateBadge.textContent = active ? "Active" : "Inactive";
  sessionStateBadge.className = `badge badge-${active ? "active" : "inactive"}`;

  sessionIdDisplay.textContent = sid;

  if (active && uptime != null) {
    const secs = Math.floor(uptime);
    sessionUptimeDisplay.textContent = `${Math.floor(secs / 60)}m ${secs % 60}s`;
  } else {
    sessionUptimeDisplay.textContent = "";
  }

  stopSessionBtn.disabled = !active;
  promptInput.disabled = !active;
  sendBtn.disabled = !active;
  openTerminalBtn.disabled = !active;

  if (!active) {
    responseViewer.disabled = true;
    responseViewer.placeholder = "(start a session to send prompts)";
    fetchBtn.disabled = true;
    insertBtn.disabled = true;
  } else {
    responseViewer.disabled = false;
    fetchBtn.disabled = false;
  }
}

// ── Session status ────────────────────────────────────────────────────────

async function fetchSessionStatus() {
  try {
    const r = await fetch(`${BRIDGE}/session/status`);
    const data = await r.json();
    render(data);
    return data;
  } catch (err) {
    debug(`fetchSessionStatus: ${err.message}`);
    return null;
  }
}

// ── Session lifecycle ────────────────────────────────────────────────────

async function startNewSession() {
  setStatus("Starting session…", "status-info");
  debug("Starting new tmux session…");
  newSessionBtn.disabled = true;
  try {
    const r = await fetch(`${BRIDGE}/session/start`, { method: "POST" });
    const data = await r.json();
    if (data.success) {
      setStatus("Session started", "status-ok");
      debug(`Session started: ${data.session_id}`);
      await fetchSessionStatus();
    } else {
      setStatus(`Error: ${data.error}`, "status-err");
      debug(`Failed: ${data.error}`);
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  } finally {
    newSessionBtn.disabled = false;
  }
}

async function stopCurrentSession() {
  setStatus("Stopping session…", "status-info");
  debug("Stopping session…");
  try {
    await fetch(`${BRIDGE}/session/stop`, { method: "POST" });
    setStatus("Session stopped", "status-ok");
    responseViewer.value = "";
    fetchBtn.disabled = true;
    insertBtn.disabled = true;
    await fetchSessionStatus();
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

// ── Prompt / Response ────────────────────────────────────────────────────

function toggleMode() {
  currentMode = currentMode === "summary" ? "raw" : "summary";
  modeToggleBtn.textContent = currentMode === "summary" ? "Summary" : "Raw";
  modeToggleBtn.className = currentMode === "summary" ? "secondary" : "accent";
}

modeToggleBtn.addEventListener("click", toggleMode);

async function sendPrompt(prompt) {
  if (!prompt.trim()) return;

  responseViewer.value = "";
  fetchBtn.disabled = true;
  insertBtn.disabled = true;
  sendBtn.disabled = true;
  setStatus("Sending prompt…", "status-info");
  debug(`Sending: ${prompt.substring(0, 60)} (mode=${currentMode})`);

  try {
    const r = await fetch(`${BRIDGE}/session/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, mode: currentMode }),
    });
    const data = await r.json();

    if (!data.success) {
      setStatus(`Error: ${data.error || "Unknown"}`, "status-err");
      responseViewer.value = `Error: ${data.error}`;
    } else {
      // Prompt sent. User watches terminal and clicks Fetch when ready.
      setStatus("Prompt sent — Fetch response when OpenCode finishes.", "status-info");
      debug("Prompt sent, waiting for user to fetch response");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
    responseViewer.value = `Failed to send prompt:\n${err.message}`;
  } finally {
    fetchBtn.disabled = false;
    sendBtn.disabled = false;
  }
}

sendBtn.addEventListener("click", () => sendPrompt(promptInput.value));
promptInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendPrompt(promptInput.value);
  }
});

// ── Fetch Response (manual) ──────────────────────────────────────────────

async function fetchResponse() {
  fetchBtn.disabled = true;
  setStatus("Fetching response…", "status-info");
  try {
    const r = await fetch(`${BRIDGE}/session/fetch-response`);
    const data = await r.json();
    if (data.success && data.response) {
      responseViewer.value = data.response;
      setStatus("Response fetched", "status-ok");
      insertBtn.disabled = false;
      debug(`Fetched response: ${data.response.length} chars`);
    } else {
      const errMsg = data.error || "No response available";
      setStatus(errMsg, "status-warn");
      debug(`Fetch failed: ${errMsg}`);
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
    debug(`Fetch error: ${err.message}`);
  } finally {
    fetchBtn.disabled = false;
  }
}

fetchBtn.addEventListener("click", fetchResponse);

// ── Insert Into ChatGPT ──────────────────────────────────────────────────

insertBtn.addEventListener("click", async () => {
  const ta = responseViewer;
  const selected = ta.value.substring(ta.selectionStart, ta.selectionEnd).trim();
  const text = selected || ta.value.trim();
  if (!text) {
    setStatus("Nothing to insert", "status-err");
    return;
  }
  setStatus("Inserting…", "status-info");
  try {
    const result = await chrome.runtime.sendMessage({
      action: "insertIntoChatGPT",
      text,
    });
    setStatus(
      result.success ? "Inserted into ChatGPT" : classifyError(result),
      result.success ? "status-ok" : "status-err",
    );
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
});

// ── Workspace ────────────────────────────────────────────────────────────

async function fetchWorkspace() {
  try {
    debug(`[DIAG] GET ${BRIDGE}/workspace`);
    const r = await fetch(`${BRIDGE}/workspace`);
    const data = await r.json();
    debug(`[DIAG] GET /workspace response: ${JSON.stringify(data)}`);
    workspacePath.textContent = data.workspace || "(not set)";
  } catch (err) {
    debug(`[DIAG] fetchWorkspace error: ${err.message}`);
  }
}

async function setWorkspace(path) {
  debug(`[DIAG A] User-selected path from UI input: "${path}"`);
  setStatus("Setting workspace…", "status-info");
  try {
    const payload = JSON.stringify({ path });
    debug(`[DIAG B] POST payload to ${BRIDGE}/workspace: ${payload}`);
    const r = await fetch(`${BRIDGE}/workspace`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
    });
    const data = await r.json();
    debug(`[DIAG B] Response status=${r.status} body=${JSON.stringify(data)}`);
    if (data.success) {
      setStatus(`Workspace: ${data.workspace}`, "status-ok");
      workspacePath.textContent = data.workspace;
      workspaceEditRow.classList.add("hidden");
      workspaceChangeBtn.classList.remove("hidden");
    } else {
      setStatus(`Error: ${data.error}`, "status-err");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

workspaceChangeBtn.addEventListener("click", () => {
  workspaceEditRow.classList.remove("hidden");
  workspaceChangeBtn.classList.add("hidden");
  workspaceInput.value = workspacePath.textContent !== "(not set)" ? workspacePath.textContent : "";
  workspaceInput.focus();
});
workspaceSetBtn.addEventListener("click", () => setWorkspace(workspaceInput.value.trim()));
workspaceCancelBtn.addEventListener("click", () => {
  workspaceEditRow.classList.add("hidden");
  workspaceChangeBtn.classList.remove("hidden");
});
workspaceInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); setWorkspace(workspaceInput.value.trim()); }
  if (e.key === "Escape") { workspaceEditRow.classList.add("hidden"); workspaceChangeBtn.classList.remove("hidden"); }
});

// ── Terminal ─────────────────────────────────────────────────────────────

async function openTerminal() {
  setStatus("Opening terminal…", "status-info");
  try {
    const r = await fetch(`${BRIDGE}/terminal/open`, { method: "POST" });
    const data = await r.json();
    if (data.need_terminal) {
      document.getElementById("terminalCmd").textContent = data.command;
      document.getElementById("terminalCmdRow").classList.remove("hidden");
      setStatus(data.error || "Run the command in a terminal", "status-warn");
    } else if (data.success) {
      setStatus("Terminal launched", "status-ok");
    } else {
      setStatus(`Error: ${data.error}`, "status-err");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

openTerminalBtn.addEventListener("click", () => {
  document.getElementById("terminalCmdRow").classList.add("hidden");
  openTerminal();
});

document.getElementById("terminalCopyBtn").addEventListener("click", () => {
  const cmd = document.getElementById("terminalCmd").textContent;
  navigator.clipboard.writeText(cmd).then(() => {
    setStatus("Command copied", "status-ok");
  }).catch(() => {
    setStatus("Failed to copy", "status-err");
  });
});

// ── Button wiring ────────────────────────────────────────────────────────

newSessionBtn.addEventListener("click", startNewSession);
stopSessionBtn.addEventListener("click", async () => {
  await stopCurrentSession();
});

// ── Diagnostics ──────────────────────────────────────────────────────────

refreshBtn.addEventListener("click", async () => {
  debug("Refreshing…");
  await fetchWorkspace();
  await fetchSessionStatus();
  debug("Refreshed");
});

pingBtn.addEventListener("click", async () => {
  debug("Pinging…");
  try {
    const r = await chrome.runtime.sendMessage({ action: "pingChatGPT" });
    debug(r.success ? `PONG (tab ${r.tabId})` : `FAIL — ${classifyError(r)}`);
  } catch (err) {
    debug(`Error: ${err.message}`);
  }
});

tabInfoBtn.addEventListener("click", async () => {
  debug("Tab info…");
  try {
    const r = await chrome.runtime.sendMessage({ action: "getTabInfo" });
    if (r.chatgptTab) debug(`ChatGPT: id=${r.chatgptTab.id}`);
    if (!r.chatgptTab && r.activeTab) debug(`Active: id=${r.activeTab.id}`);
  } catch (err) {
    debug(`Error: ${err.message}`);
  }
});

// ── Context menu integration ─────────────────────────────────────────────

chrome.storage.session.onChanged.addListener((changes) => {
  if (changes.pendingPrompt) {
    const prompt = changes.pendingPrompt.newValue;
    if (prompt) {
      debug(`Context menu prompt: ${prompt.substring(0, 60)}`);
      promptInput.value = prompt;
      sendPrompt(prompt);
    }
  }
});

// ── Init ─────────────────────────────────────────────────────────────────

chrome.storage.session.get(["pendingPrompt", "panelState"], (result) => {
  if (result.pendingPrompt) {
    const prompt = result.pendingPrompt;
    promptInput.value = prompt;
    chrome.storage.session.remove(["pendingPrompt", "panelState"]);
    sendPrompt(prompt);
  }

  fetchWorkspace();
  fetchSessionStatus();
  fetchDebugStatus();

  statusPollInterval = setInterval(fetchSessionStatus, 5000);
});

window.addEventListener("unload", () => {
  if (statusPollInterval) clearInterval(statusPollInterval);
});

// ── Error classifier ─────────────────────────────────────────────────────

function classifyError(result) {
  switch (result.error) {
    case "no_chatgpt_tab":       return "No ChatGPT tab. Open chatgpt.com first.";
    case "content_script_missing": return "Reload chatgpt.com and try again.";
    case "insertion_failed":     return `Insertion failed: ${result.detail || "unknown"}`;
    default:                     return result.detail || result.error || "Unknown error.";
  }
}
