const BRIDGE = "http://localhost:7777";

// ── Page navigation ──────────────────────────────────────────────────────

const pageMgmt   = document.getElementById("page-mgmt");
const pageActive = document.getElementById("page-active");
const backBtn    = document.getElementById("backToMgmtBtn");

function showPage(page) {
  pageMgmt.classList.toggle("hidden", page !== "mgmt");
  pageActive.classList.toggle("hidden", page !== "active");
}

backBtn.addEventListener("click", () => showPage("mgmt"));

// ── DOM refs ─────────────────────────────────────────────────────────────

const statusEl           = document.getElementById("status");
const debugLog           = document.getElementById("debugLog");

// Page 1 — management
const newSessionBtn      = document.getElementById("newSessionBtn");
const savedSessionList   = document.getElementById("savedSessionList");
const mgmtWorkspacePath  = document.getElementById("mgmtWorkspacePath");
const mgmtSessionState   = document.getElementById("mgmtSessionState");
const mgmtSessionId      = document.getElementById("mgmtSessionId");
const mgmtSessionUptime  = document.getElementById("mgmtSessionUptime");
const mgmtSessionSource  = document.getElementById("mgmtSessionSource");
const mgmtOpenTerminalBtn= document.getElementById("mgmtOpenTerminalBtn");

// Page 2 — active session
const promptInput        = document.getElementById("promptInput");
const sendBtn            = document.getElementById("sendBtn");
const responseViewer     = document.getElementById("responseViewer");
const insertBtn          = document.getElementById("insertBtn");
const activeSessionInfo  = document.getElementById("activeSessionInfo");
const activeOpenTerminalBtn = document.getElementById("activeOpenTerminalBtn");
const activeStopBtn      = document.getElementById("activeStopBtn");

// Workspace (shared, lives on page 1 but accessible everywhere)
const workspaceChangeBtn = document.getElementById("workspaceChangeBtn");
const workspaceEditRow   = document.getElementById("workspaceEditRow");
const workspaceInput     = document.getElementById("workspaceInput");
const workspaceSetBtn    = document.getElementById("workspaceSetBtn");
const workspaceCancelBtn = document.getElementById("workspaceCancelBtn");

// Mode toggle
const modeToggleBtn      = document.getElementById("modeToggleBtn");
let currentMode          = "summary"; // "summary" | "raw"

// Diagnostics
const pingBtn            = document.getElementById("pingBtn");
const tabInfoBtn         = document.getElementById("tabInfoBtn");
const refreshBtn         = document.getElementById("refreshBtn");

// ── State ────────────────────────────────────────────────────────────────

let statusPollInterval = null;

// ── Helpers ──────────────────────────────────────────────────────────────

function setStatus(msg, cls) {
  statusEl.textContent = msg;
  statusEl.className = cls || "status-info";
}

function debug(msg) {
  debugLog.classList.remove("hidden");
  debugLog.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
  debugLog.scrollTop = debugLog.scrollHeight;
}

// ── Session status (shared) ──────────────────────────────────────────────

async function fetchSessionStatus() {
  try {
    const r = await fetch(`${BRIDGE}/session/status`);
    const data = await r.json();
    applySessionStatus(data);
    return data;
  } catch (err) {
    debug(`fetchSessionStatus: ${err.message}`);
    return null;
  }
}

function applySessionStatus(data) {
  if (!data) return;
  const active = data.active;

  // Page 1 indicators
  mgmtSessionState.textContent = active ? "Active" : "Inactive";
  mgmtSessionState.className = `badge badge-${active ? "active" : "inactive"}`;
  mgmtSessionId.textContent = data.session_id || "—";
  mgmtOpenTerminalBtn.disabled = !active;
  mgmtSessionSource.textContent = data.source || "bridge";

  if (data.uptime != null) {
    const secs = Math.floor(data.uptime);
    mgmtSessionUptime.textContent = `${Math.floor(secs / 60)}m ${secs % 60}s`;
  } else {
    mgmtSessionUptime.textContent = "—";
  }

  if (data.workspace && data.workspace.workspace) {
    mgmtWorkspacePath.textContent = data.workspace.workspace;
  }

  // Page 2 indicator
  activeSessionInfo.textContent = active
    ? `Active (${data.session_id || ""})`
    : "Inactive";
  activeOpenTerminalBtn.disabled = !active;
  activeStopBtn.disabled = !active;
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
      showPage("active");
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
    await fetchSessionStatus();
    showPage("mgmt");
    await fetchSavedSessions();
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

// ── Prompt / Response ────────────────────────────────────────────────────

function toggleMode() {
  currentMode = currentMode === "summary" ? "raw" : "summary";
  modeToggleBtn.textContent = currentMode === "summary" ? "Summary" : "Raw";
  modeToggleBtn.className = currentMode === "summary" ? "secondary" : "accent";
  setStatus(`Mode: ${currentMode}`, "status-info");
}

modeToggleBtn.addEventListener("click", toggleMode);

async function sendPrompt(prompt) {
  if (!prompt.trim()) return;

  responseViewer.value = "";
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
    const { prompt_id, success, error } = await r.json();

    if (!success) {
      setStatus(`Error: ${error || "Unknown"}`, "status-err");
      responseViewer.value = `Error: ${error}`;
      sendBtn.disabled = false;
      return;
    }

    // Poll for progress
    const pollUrl = `${BRIDGE}/session/prompt-status/${prompt_id}`;
    let done = false;

    while (!done) {
      await new Promise((r) => setTimeout(r, 500));
      const pr = await fetch(pollUrl);
      const ps = await pr.json();

      if (ps.error) {
        setStatus(`Error: ${ps.error}`, "status-err");
        break;
      }

      if (ps.progress) {
        responseViewer.value = ps.progress;
      }

      if (ps.done) {
        done = true;
        if (ps.error) {
          setStatus(`Error: ${ps.error}`, "status-err");
          responseViewer.value = `Error: ${ps.error}`;
        } else {
          const finalText = ps.result || ps.progress || "";
          responseViewer.value = finalText || "(no output)";
          if (finalText) {
            setStatus("Response ready", "status-ok");
            insertBtn.disabled = false;
          } else {
            setStatus("Empty response", "status-err");
          }
        }
      } else {
        if (currentMode === "summary") {
          const dots = ".".repeat((Math.floor(Date.now() / 1000) % 3) + 1);
          setStatus(`Running${dots}`, "status-info");
        } else {
          setStatus("Running (raw)", "status-err");
        }
      }
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
    responseViewer.value = `Failed to send prompt:\n${err.message}`;
  } finally {
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

// ── Session history ──────────────────────────────────────────────────────

async function fetchSavedSessions() {
  try {
    const r = await fetch(`${BRIDGE}/sessions`);
    const data = await r.json();
    renderSavedSessions(data.sessions || []);
  } catch (err) {
    debug(`fetchSavedSessions: ${err.message}`);
  }
}

function renderSavedSessions(sessions) {
  if (!sessions.length) {
    savedSessionList.innerHTML =
      '<div style="color:#585b70;text-align:center;padding:12px;font-size:11px;">No saved sessions</div>';
    return;
  }
  savedSessionList.innerHTML = sessions
    .slice(0, 20)
    .map((s) => {
      const title = s.title || s.session_id;
      const updated = s.updated || "?";
      return `<div class="session-list-item">
        <div>
          <div class="sli-id" title="${s.session_id}">${title}</div>
          <div class="sli-meta">${s.session_id}</div>
          <div class="sli-meta">${updated} · from OpenCode</div>
        </div>
        <div class="sli-actions">
          <button class="secondary" data-load="${s.session_id}">Load</button>
          <button class="secondary" data-delete="${s.session_id}">Delete</button>
        </div>
      </div>`;
    })
    .join("");

  savedSessionList.querySelectorAll("[data-load]").forEach((btn) => {
    btn.addEventListener("click", () => loadSession(btn.dataset.load));
  });
  savedSessionList.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", () => deleteSession(btn.dataset.delete));
  });
}

async function loadSession(sessionId) {
  setStatus("Loading session…", "status-info");
  debug(`Loading session: ${sessionId}`);
  try {
    const r = await fetch(`${BRIDGE}/sessions/load/${sessionId}`, { method: "POST" });
    const data = await r.json();
    if (data.success) {
      setStatus("Session loaded", "status-ok");
      await fetchSessionStatus();
      showPage("active");
      await fetchSavedSessions();
    } else {
      setStatus(`Error: ${data.error}`, "status-err");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

async function deleteSession(sessionId) {
  if (!confirm(`Delete session ${sessionId}?`)) return;
  debug(`Deleting session: ${sessionId}`);
  try {
    const r = await fetch(`${BRIDGE}/sessions/${sessionId}`, { method: "DELETE" });
    const data = await r.json();
    if (data.success) {
      setStatus("Session deleted", "status-ok");
      await fetchSavedSessions();
    } else {
      setStatus(`Error: ${data.error}`, "status-err");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

// ── Workspace ────────────────────────────────────────────────────────────

async function fetchWorkspace() {
  try {
    const r = await fetch(`${BRIDGE}/workspace`);
    const data = await r.json();
    mgmtWorkspacePath.textContent = data.workspace || "(not set)";
  } catch (err) {
    debug(`fetchWorkspace: ${err.message}`);
  }
}

async function setWorkspace(path) {
  setStatus("Setting workspace…", "status-info");
  try {
    const r = await fetch(`${BRIDGE}/workspace`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await r.json();
    if (data.success) {
      setStatus(`Workspace: ${data.workspace}`, "status-ok");
      mgmtWorkspacePath.textContent = data.workspace;
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
  workspaceInput.value = mgmtWorkspacePath.textContent !== "(not set)" ? mgmtWorkspacePath.textContent : "";
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
    setStatus(
      data.success ? "Terminal launched" : `Error: ${data.error}`,
      data.success ? "status-ok" : "status-err",
    );
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

mgmtOpenTerminalBtn.addEventListener("click", openTerminal);
activeOpenTerminalBtn.addEventListener("click", openTerminal);

// ── Button wiring ────────────────────────────────────────────────────────

newSessionBtn.addEventListener("click", startNewSession);
activeStopBtn.addEventListener("click", async () => {
  await stopCurrentSession();
  await fetchSavedSessions();
});

// ── Diagnostics ──────────────────────────────────────────────────────────

refreshBtn.addEventListener("click", async () => {
  debug("Refreshing…");
  await fetchWorkspace();
  await fetchSessionStatus();
  await fetchSavedSessions();
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
      showPage("active");
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
    showPage("active");
    sendPrompt(prompt);
  } else {
    debug("Side panel loaded");
  }

  fetchWorkspace();
  fetchSessionStatus();
  fetchSavedSessions();

  statusPollInterval = setInterval(async () => {
    const data = await fetchSessionStatus();
    if (data && data.active) {
      // Refresh saved sessions list to show updated prompt count
      await fetchSavedSessions();
    }
  }, 5000);
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
