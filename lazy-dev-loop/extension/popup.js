const responseEl = document.getElementById("response");
const insertBtn = document.getElementById("insertBtn");
const statusEl = document.getElementById("status");
const pingBtn = document.getElementById("pingBtn");
const tabInfoBtn = document.getElementById("tabInfoBtn");
const debugLog = document.getElementById("debugLog");

function debug(msg) {
  debugLog.classList.remove("hidden");
  debugLog.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
  debugLog.scrollTop = debugLog.scrollHeight;
}

chrome.storage.session.get("lastResponse", (result) => {
  const text = result.lastResponse;
  if (text) {
    responseEl.value = text;
    responseEl.classList.remove("empty");
    insertBtn.disabled = false;
    statusEl.textContent = "Select part of the response or click Insert to add all of it.";
    statusEl.className = "status-hint";
  } else {
    responseEl.value = "No response yet. Highlight some text, right-click, and choose 'Send To OpenCode'.";
    responseEl.classList.add("empty");
    insertBtn.disabled = true;
  }
});

insertBtn.addEventListener("click", async () => {
  const fullText = responseEl.value;
  const selected =
    responseEl.selectionStart !== responseEl.selectionEnd
      ? fullText.substring(responseEl.selectionStart, responseEl.selectionEnd)
      : null;

  const textToInsert = selected || fullText;

  statusEl.textContent = "Inserting…";
  statusEl.className = "status-hint";

  try {
    const result = await chrome.runtime.sendMessage({
      action: "insertIntoChatGPT",
      text: textToInsert,
    });

    if (result.success) {
      statusEl.textContent = "Inserted into ChatGPT";
      statusEl.className = "status-success";
    } else {
      statusEl.textContent = classifyError(result) || "Insertion failed.";
      statusEl.className = "status-error";
    }
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
    statusEl.className = "status-error";
  }
});

pingBtn.addEventListener("click", async () => {
  debug("Pinging ChatGPT tab…");
  try {
    const result = await chrome.runtime.sendMessage({ action: "pingChatGPT" });
    if (result.success) {
      debug(`PONG — content script alive (tab ${result.tabId})`);
    } else {
      debug(`PING failed — ${classifyError(result)}`);
    }
  } catch (err) {
    debug(`PING error — ${err.message}`);
  }
});

tabInfoBtn.addEventListener("click", async () => {
  debug("Fetching tab info…");
  try {
    const result = await chrome.runtime.sendMessage({ action: "getTabInfo" });
    if (result.chatgptTab) {
      debug(`ChatGPT tab: id=${result.chatgptTab.id} url=${result.chatgptTab.url} title=${result.chatgptTab.title}`);
    } else {
      debug("No ChatGPT tab found.");
      if (result.activeTab) {
        debug(`Active tab: id=${result.activeTab.id} url=${result.activeTab.url} title=${result.activeTab.title}`);
      } else {
        debug("No active tab found.");
      }
    }
  } catch (err) {
    debug(`Tab info error — ${err.message}`);
  }
});

function classifyError(result) {
  switch (result.error) {
    case "no_chatgpt_tab":
      return "No ChatGPT tab found. Open chatgpt.com first.";
    case "content_script_missing":
      return "Content script not loaded. Reload chatgpt.com and try again.";
    case "insertion_failed":
      return `Insertion failed: ${result.detail || "unknown"}`;
    case "ping_failed":
      return `Content script unreachable: ${result.detail || "unknown"}`;
    case "unknown":
      return `Unexpected error: ${result.detail || "unknown"}`;
    default:
      return result.detail || result.error || "Unknown error.";
  }
}
