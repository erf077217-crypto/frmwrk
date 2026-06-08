const BRIDGE = "http://localhost:7777";

const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");
const responseViewer = document.getElementById("responseViewer");
const insertBtn = document.getElementById("insertBtn");
const statusEl = document.getElementById("status");
const pingBtn = document.getElementById("pingBtn");
const tabInfoBtn = document.getElementById("tabInfoBtn");
const refreshBtn = document.getElementById("refreshBtn");
const debugLog = document.getElementById("debugLog");

const workspacePath = document.getElementById("workspacePath");
const workspaceChangeBtn = document.getElementById("workspaceChangeBtn");
const workspaceEditRow = document.getElementById("workspaceEditRow");
const workspaceInput = document.getElementById("workspaceInput");
const workspaceSetBtn = document.getElementById("workspaceSetBtn");
const workspaceCancelBtn = document.getElementById("workspaceCancelBtn");

const sessionState = document.getElementById("sessionState");
const sessionId = document.getElementById("sessionId");
const sessionPid = document.getElementById("sessionPid");
const sessionUptime = document.getElementById("sessionUptime");
const sessionPort = document.getElementById("sessionPort");
const sessionStartBtn = document.getElementById("sessionStartBtn");
const sessionStopBtn = document.getElementById("sessionStopBtn");
const openTerminalBtn = document.getElementById("openTerminalBtn");

let fullResponse = "";
let statusPollInterval = null;

function setStatus(msg, cls) {
  statusEl.textContent = msg;
  statusEl.className = cls || "status-info";
}

function debug(msg) {
  debugLog.classList.remove("hidden");
  debugLog.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
  debugLog.scrollTop = debugLog.scrollHeight;
}

// -------------------------------------------------------------------------
// Workspace
// -------------------------------------------------------------------------

async function fetchWorkspace() {
  try {
    const r = await fetch(`${BRIDGE}/workspace`);
    const data = await r.json();
    if (data.workspace) {
      workspacePath.textContent = data.workspace;
    } else {
      workspacePath.textContent = "(not set)";
    }
  } catch (err) {
    debug(`fetchWorkspace error: ${err.message}`);
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

workspaceSetBtn.addEventListener("click", () => {
  setWorkspace(workspaceInput.value.trim());
});

workspaceCancelBtn.addEventListener("click", () => {
  workspaceEditRow.classList.add("hidden");
  workspaceChangeBtn.classList.remove("hidden");
});

workspaceInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    setWorkspace(workspaceInput.value.trim());
  }
  if (e.key === "Escape") {
    workspaceEditRow.classList.add("hidden");
    workspaceChangeBtn.classList.remove("hidden");
  }
});

// -------------------------------------------------------------------------
// Session
// -------------------------------------------------------------------------

async function fetchSessionStatus() {
  try {
    const r = await fetch(`${BRIDGE}/session/status`);
    const data = await r.json();
    updateSessionUI(data);
    return data;
  } catch (err) {
    debug(`fetchSessionStatus error: ${err.message}`);
    return null;
  }
}

function updateSessionUI(data) {
  if (!data) return;

  const active = data.active;

  if (active) {
    sessionState.textContent = "Active";
    sessionState.className = "badge badge-active";
    sessionId.textContent = data.session_id || "—";
    sessionPid.textContent = data.pid || "—";
    sessionPort.textContent = data.port || "—";
    if (data.uptime != null) {
      const secs = Math.floor(data.uptime);
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      sessionUptime.textContent = `${m}m ${s}s`;
    } else {
      sessionUptime.textContent = "—";
    }
    sessionStartBtn.disabled = true;
    sessionStopBtn.disabled = false;
    openTerminalBtn.disabled = false;
  } else {
    sessionState.textContent = "Inactive";
    sessionState.className = "badge badge-inactive";
    sessionId.textContent = "—";
    sessionPid.textContent = "—";
    sessionUptime.textContent = "—";
    sessionPort.textContent = "—";
    sessionStartBtn.disabled = false;
    sessionStopBtn.disabled = true;
    openTerminalBtn.disabled = true;
  }

  if (data.workspace && data.workspace.workspace) {
    workspacePath.textContent = data.workspace.workspace;
  }
}

async function startSession() {
  setStatus("Starting session…", "status-info");
  debug("Starting OpenCode session…");
  sessionStartBtn.disabled = true;
  try {
    const r = await fetch(`${BRIDGE}/session/start`, { method: "POST" });
    const data = await r.json();
    if (data.success) {
      setStatus(`Session started (PID: ${data.pid})`, "status-ok");
      debug(`Session started: ${data.session_id} on port ${data.port}`);
    } else {
      setStatus(`Error: ${data.error}`, "status-err");
      debug(`Failed to start session: ${data.error}`);
    }
    await fetchSessionStatus();
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
    sessionStartBtn.disabled = false;
  }
}

async function stopSession() {
  setStatus("Stopping session…", "status-info");
  debug("Stopping OpenCode session…");
  try {
    const r = await fetch(`${BRIDGE}/session/stop`, { method: "POST" });
    const data = await r.json();
    if (data.success) {
      setStatus("Session stopped", "status-ok");
      debug("Session stopped");
    }
    await fetchSessionStatus();
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
}

sessionStartBtn.addEventListener("click", startSession);
sessionStopBtn.addEventListener("click", stopSession);

// -------------------------------------------------------------------------
// Send prompt
// -------------------------------------------------------------------------

async function sendPrompt(prompt) {
  if (!prompt.trim()) return;

  fullResponse = "";
  responseViewer.textContent = "(sending…)";
  insertBtn.disabled = true;
  sendBtn.disabled = true;
  setStatus("Sending prompt…", "status-info");
  debug(`Sending prompt: ${prompt.substring(0, 60)}`);

  try {
    const r = await fetch(`${BRIDGE}/session/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const data = await r.json();

    if (data.success) {
      fullResponse = data.output || "(no output)";
      responseViewer.textContent = fullResponse;
      setStatus("Response ready", "status-ok");
      insertBtn.disabled = false;
    } else {
      setStatus(`Error: ${data.error || "Unknown"}`, "status-err");
      responseViewer.textContent = data.output || `Error: ${data.error}`;
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
    responseViewer.textContent = `Failed to send prompt:\n${err.message}`;
  } finally {
    sendBtn.disabled = false;
  }
}

sendBtn.addEventListener("click", () => {
  sendPrompt(promptInput.value);
});

promptInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.shiftKey === false) {
    e.preventDefault();
    sendPrompt(promptInput.value);
  }
});

// -------------------------------------------------------------------------
// Open Terminal
// -------------------------------------------------------------------------

openTerminalBtn.addEventListener("click", async () => {
  setStatus("Opening terminal…", "status-info");
  try {
    const r = await fetch(`${BRIDGE}/terminal/open`, { method: "POST" });
    const data = await r.json();
    if (data.success) {
      setStatus("Terminal launched", "status-ok");
      debug("Terminal window opened");
    } else {
      setStatus(`Error: ${data.error}`, "status-err");
      debug(`Terminal launch failed: ${data.error}`);
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
});

// -------------------------------------------------------------------------
// Insert into ChatGPT
// -------------------------------------------------------------------------

insertBtn.addEventListener("click", async () => {
  const selected = window.getSelection().toString().trim();
  const textToInsert = selected || fullResponse;

  if (!textToInsert) {
    setStatus("Nothing to insert", "status-err");
    return;
  }

  setStatus("Inserting…", "status-info");

  try {
    const result = await chrome.runtime.sendMessage({
      action: "insertIntoChatGPT",
      text: textToInsert,
    });

    if (result.success) {
      setStatus("Inserted into ChatGPT", "status-ok");
    } else {
      setStatus(classifyError(result), "status-err");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "status-err");
  }
});

// -------------------------------------------------------------------------
// Diagnostics
// -------------------------------------------------------------------------

refreshBtn.addEventListener("click", async () => {
  debug("Refreshing status…");
  await fetchWorkspace();
  await fetchSessionStatus();
  debug("Status refreshed");
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
    if (r.chatgptTab) {
      debug(`ChatGPT: id=${r.chatgptTab.id} url=${r.chatgptTab.url}`);
    } else {
      debug("No ChatGPT tab found");
      if (r.activeTab) debug(`Active: id=${r.activeTab.id} url=${r.activeTab.url}`);
    }
  } catch (err) {
    debug(`Error: ${err.message}`);
  }
});

// -------------------------------------------------------------------------
// Context menu integration
// -------------------------------------------------------------------------

chrome.storage.session.onChanged.addListener((changes) => {
  if (changes.pendingPrompt) {
    const prompt = changes.pendingPrompt.newValue;
    if (prompt) {
      debug(`New prompt from context menu: ${prompt.substring(0, 60)}`);
      promptInput.value = prompt;
      sendPrompt(prompt);
    }
  }
});

chrome.storage.session.get(["pendingPrompt", "panelState"], (result) => {
  if (result.pendingPrompt) {
    const prompt = result.pendingPrompt;
    debug(`Pending prompt detected: ${prompt.substring(0, 60)}`);
    promptInput.value = prompt;
    chrome.storage.session.remove(["pendingPrompt", "panelState"]);
    sendPrompt(prompt);
  } else {
    debug("Side panel loaded (idle)");
  }

  fetchWorkspace();
  fetchSessionStatus();

  statusPollInterval = setInterval(fetchSessionStatus, 5000);
});

window.addEventListener("unload", () => {
  if (statusPollInterval) clearInterval(statusPollInterval);
});

// -------------------------------------------------------------------------
// Error classifier
// -------------------------------------------------------------------------

function classifyError(result) {
  switch (result.error) {
    case "no_chatgpt_tab":
      return "No ChatGPT tab. Open chatgpt.com first.";
    case "content_script_missing":
      return "Reload chatgpt.com and try again.";
    case "insertion_failed":
      return `Insertion failed: ${result.detail || "unknown"}`;
    default:
      return result.detail || result.error || "Unknown error.";
  }
}
